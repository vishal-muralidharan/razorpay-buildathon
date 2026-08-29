from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, audit
from app.database import get_db
from app.scheduler import decide_retry, MAX_RETRIES
from app.nudge import build_message, build_self_schedule_options, send_nudge
from app.razorpay_client import attempt_recurring_debit
from app.scheduler_setup import scheduler
from app.jobs import execute_retry_job

router = APIRouter(tags=["scheduling"])


@router.post("/schedule-retry", response_model=schemas.ScheduleRetryResponse)
def schedule_retry(req: schemas.ScheduleRetryRequest, db: Session = Depends(get_db)):
    txn = db.query(models.FailedTransaction).get(req.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Hard compliance gate - reject a 4th attempt outright.
    if txn.retry_count >= MAX_RETRIES:
        audit.log_step(db, txn.id, "SCHEDULING_REJECTED", {
            "reason": "NPCI 3-retry cap already reached", "retry_count": txn.retry_count,
        })
        raise HTTPException(
            status_code=400,
            detail=f"NPCI compliance cap reached ({txn.retry_count}/{MAX_RETRIES} attempts used). "
                   "No further retries permitted this billing cycle.",
        )

    # If the customer already self-scheduled a future date, auto-retry stays paused.
    if txn.status == models.TransactionStatus.AWAITING_CUSTOMER.value and txn.customer_chosen_date:
        if datetime.now(timezone.utc) < txn.customer_chosen_date:
            audit.log_step(db, txn.id, "SCHEDULING_PAUSED", {
                "reason": "Customer self-scheduled a date; automated retry stays paused until then.",
                "customer_chosen_date": txn.customer_chosen_date,
            })
            return schemas.ScheduleRetryResponse(
                transaction_id=txn.id,
                scheduled_time=txn.customer_chosen_date,
                attempts_used=txn.retry_count,
                attempts_remaining=MAX_RETRIES - txn.retry_count,
                reason="Automated retries paused - customer chose their own retry date.",
                status=txn.status,
            )

    decision = decide_retry(db, txn)

    if not decision["allowed"]:
        txn.status = decision["new_status"]
        db.commit()
        audit.log_step(db, txn.id, "SCHEDULING_BLOCKED", {
            "reason": decision["reason"], "new_status": decision["new_status"],
        })
        return schemas.ScheduleRetryResponse(
            transaction_id=txn.id,
            scheduled_time=None,
            attempts_used=txn.retry_count,
            attempts_remaining=MAX_RETRIES - txn.retry_count,
            reason=decision["reason"],
            status=txn.status,
        )

    # Consume one NPCI-permitted attempt slot for this scheduling decision.
    txn.retry_count += 1
    txn.status = decision["new_status"]
    new_decision = models.RetryDecision(
        transaction_id=txn.id,
        attempt_number=txn.retry_count,
        chosen_slot_time=decision["scheduled_time"],
        predicted_success_prob=decision["predicted_success_prob"],
        reason=decision["reason"],
    )
    db.add(new_decision)
    db.commit()

    # Add job to APScheduler
    scheduler.add_job(
        execute_retry_job, 
        'date', 
        run_date=new_decision.chosen_slot_time, 
        args=[new_decision.id], 
        id=f"retry-{new_decision.id}", 
        misfire_grace_time=3600,
        replace_existing=True
    )

    audit.log_step(db, txn.id, "RETRY_SCHEDULED", {
        "attempt_number": txn.retry_count,
        "scheduled_time": decision["scheduled_time"],
        "predicted_success_prob": decision["predicted_success_prob"],
        "reason": decision["reason"],
    })

    # Fire the customer nudge for this decision.
    customer = db.query(models.Customer).get(txn.customer_id)
    mandate = txn.mandate
    message = build_message(
        category=txn.decline_category,
        customer_name=customer.name,
        merchant=mandate.merchant_name,
        amount=txn.amount,
        mandate_date=txn.failed_at,
        recommended_date=decision["scheduled_time"],
    )
    options = build_self_schedule_options(decision["scheduled_time"])
    send_result = send_nudge(customer.phone, message, channel="whatsapp")

    import json
    db.add(models.NudgeLog(
        transaction_id=txn.id,
        channel="whatsapp",
        message=message,
        self_schedule_options=json.dumps(options),
        simulated=send_result.get("simulated", True),
    ))
    db.commit()

    audit.log_step(db, txn.id, "NUDGE_SENT", {
        "channel": "whatsapp", "message": message, "self_schedule_options": options,
        "send_result": send_result,
    })

    return schemas.ScheduleRetryResponse(
        transaction_id=txn.id,
        scheduled_time=decision["scheduled_time"],
        attempts_used=txn.retry_count,
        attempts_remaining=MAX_RETRIES - txn.retry_count,
        reason=decision["reason"],
        status=txn.status,
    )


@router.post("/execute-retry", response_model=schemas.ExecuteRetryResponse)
def execute_retry(req: schemas.ExecuteRetryRequest, db: Session = Depends(get_db)):
    """Executes the most recent scheduled retry decision against Razorpay
    test-mode (or the simulator). In production this would be invoked by
    APScheduler when a decision's chosen_slot_time arrives; exposed here as
    a direct endpoint so the demo can trigger it on cue."""
    txn = db.query(models.FailedTransaction).get(req.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    decision = (
        db.query(models.RetryDecision)
        .filter(models.RetryDecision.transaction_id == txn.id)
        .order_by(models.RetryDecision.id.desc())
        .first()
    )
    if not decision or decision.outcome != "PENDING":
        raise HTTPException(status_code=400, detail="No pending scheduled retry to execute for this transaction.")

    result = execute_retry_job(decision.id)
    
    db.refresh(txn)
    db.refresh(decision)

    return schemas.ExecuteRetryResponse(
        transaction_id=txn.id,
        outcome=decision.outcome,
        razorpay_payment_id=result.get("razorpay_payment_id") if result else None,
        status=txn.status,
        attempts_used=txn.retry_count,
    )
