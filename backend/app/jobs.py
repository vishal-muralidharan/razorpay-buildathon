from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models, audit
from app.razorpay_client import attempt_recurring_debit
from app.scheduler import MAX_RETRIES, BANK_OUTAGE_RECHECK_HOURS, _push_out_of_peak_hours
from app.scheduler_setup import scheduler

def execute_retry_job(decision_id: int):
    db: Session = SessionLocal()
    try:
        # 1. Fetch decision with FOR UPDATE lock to prevent double-execution
        decision = db.query(models.RetryDecision).with_for_update().get(decision_id)
        if not decision or decision.outcome != "PENDING":
            return  # Already executed or doesn't exist

        txn = decision.transaction
        
        # 2. Bank Outage check
        if txn.decline_category == "BANK_OUTAGE":
            bank_status = db.query(models.BankStatus).filter(models.BankStatus.bank_name == txn.mandate.bank_name).first()
            if not bank_status or bank_status.status == "DOWN":
                # Still down, reschedule
                now = datetime.now(timezone.utc)
                new_slot = _push_out_of_peak_hours(now + timedelta(hours=BANK_OUTAGE_RECHECK_HOURS))
                decision.chosen_slot_time = new_slot
                decision.reason = f"BANK_OUTAGE at {txn.mandate.bank_name} still ongoing (status=DOWN) - rescheduled by {BANK_OUTAGE_RECHECK_HOURS}h."
                db.commit()
                
                # Update job in APScheduler
                scheduler.add_job(
                    execute_retry_job, 
                    'date', 
                    run_date=new_slot, 
                    args=[decision.id], 
                    id=f"retry-{decision.id}", 
                    misfire_grace_time=3600,
                    replace_existing=True
                )
                
                audit.log_step(db, txn.id, "RETRY_RESCHEDULED_BANK_OUTAGE", {
                    "attempt_number": decision.attempt_number,
                    "new_scheduled_time": new_slot,
                })
                return
        
        # 3. Proceed with execution
        result = attempt_recurring_debit(
            amount=txn.amount,
            predicted_success_prob=decision.predicted_success_prob,
            notes={"transaction_id": txn.id, "customer_id": txn.customer_id},
        )

        success = result.get("status") == "captured"
        decision.outcome = "SUCCESS" if success else "FAILURE"
        
        if success:
            txn.status = models.TransactionStatus.RECOVERED.value
            txn.recovered_at = datetime.now(timezone.utc)
        else:
            txn.status = (
                models.TransactionStatus.EXHAUSTED.value
                if txn.retry_count >= MAX_RETRIES
                else models.TransactionStatus.PENDING.value
            )
            
        db.commit()
        
        audit.log_step(db, txn.id, "RETRY_EXECUTED", {
            "attempt_number": decision.attempt_number,
            "outcome": decision.outcome,
            "razorpay_result": result,
        })
    finally:
        db.close()


def reconciliation_sweep_job():
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Find PENDING decisions whose chosen slot is in the past
        stale_decisions = (
            db.query(models.RetryDecision)
            .filter(models.RetryDecision.outcome == "PENDING")
            .filter(models.RetryDecision.chosen_slot_time < now)
            .all()
        )
        
        for decision in stale_decisions:
            job_id = f"retry-{decision.id}"
            job = scheduler.get_job(job_id)
            if not job:
                # Job is missing, add it to run immediately
                scheduler.add_job(
                    execute_retry_job, 
                    'date', 
                    run_date=now, 
                    args=[decision.id], 
                    id=job_id, 
                    misfire_grace_time=3600,
                    replace_existing=True
                )
                
                audit.log_step(db, decision.transaction_id, "RECONCILIATION_SWEEP", {
                    "decision_id": decision.id,
                    "action": "Job was missing from scheduler. Recreated."
                })
    finally:
        db.close()
