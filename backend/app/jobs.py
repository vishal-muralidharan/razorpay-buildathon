import random
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
        idempotency_key = f"txn_{txn.id}_attempt_{decision.attempt_number}"
        
        rzp_customer_id = txn.mandate.razorpay_customer_id or "cust_dummy"
        rzp_token_id = txn.mandate.razorpay_token_id or "token_dummy"

        result = attempt_recurring_debit(
            amount=txn.amount,
            predicted_success_prob=decision.predicted_success_prob,
            notes={
                "transaction_id": txn.id, 
                "customer_id": txn.customer_id,
                "decision_id": decision.id
            },
            razorpay_customer_id=rzp_customer_id,
            razorpay_token_id=rzp_token_id,
            idempotency_key=idempotency_key,
        )

        if result.get("simulated"):
            # No real Razorpay webhook will ever arrive for a simulated
            # attempt, so resolve the outcome immediately here instead of
            # leaving the transaction stuck in PENDING_CONFIRMATION forever.
            # Success probability mirrors the liquidity predictor's
            # confidence score, so better-timed retries visibly succeed
            # more often in the demo.
            success = random.random() < max(0.15, min(decision.predicted_success_prob, 0.95))
            decision.outcome = "SUCCESS" if success else "FAILURE"
            result["status"] = "captured" if success else "failed"
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
                "idempotency_key": idempotency_key,
                "outcome": decision.outcome,
                "razorpay_result": result,
                "note": "Simulated attempt - resolved locally, no real webhook expected.",
            })
        else:
            # Real Razorpay call was placed successfully; the actual
            # captured/failed outcome will arrive asynchronously via
            # POST /webhook/razorpay and resolve decision.outcome then.
            txn.status = models.TransactionStatus.PENDING_CONFIRMATION.value
            db.commit()

            audit.log_step(db, txn.id, "RETRY_INITIATED", {
                "attempt_number": decision.attempt_number,
                "idempotency_key": idempotency_key,
                "razorpay_result": result,
            })

        return result
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


def detect_bank_outages_job():
    """Runs every 5 minutes to infer bank outages from recent decline spikes.
    
    TODO (Live Bank Status):
    This infers outages from our own decline-rate spikes since there's no public 
    NPCI/bank uptime feed to subscribe to. Keep this as the baseline fallback. 
    If a payment partner (e.g. Razorpay, Setu) offers a real live feed to plug 
    in instead, pipe those into the already existing `POST /webhook/bank-status` 
    endpoint to instantly update the BankStatus table.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        five_mins_ago = now - timedelta(minutes=5)
        
        # Get all failed transactions in the last 5 minutes
        recent_failures = (
            db.query(models.FailedTransaction)
            .filter(models.FailedTransaction.failed_at >= five_mins_ago)
            .all()
        )
        
        # Group by bank
        from collections import defaultdict
        bank_stats = defaultdict(lambda: {"total": 0, "outages": 0})
        
        for txn in recent_failures:
            bank_name = txn.mandate.bank_name
            bank_stats[bank_name]["total"] += 1
            if txn.decline_category == "BANK_OUTAGE":
                bank_stats[bank_name]["outages"] += 1
                
        # Update BankStatus for all banks
        all_banks = db.query(models.BankStatus).all()
        for bank in all_banks:
            stats = bank_stats.get(bank.bank_name, {"total": 0, "outages": 0})
            
            # Outage condition: > 3 failures in 5 mins AND > 50% are BANK_OUTAGE
            if stats["total"] >= 3 and (stats["outages"] / stats["total"]) > 0.5:
                if bank.status != "DOWN":
                    bank.status = "DOWN"
                    bank.updated_at = now
                    print(f"BankOutageDetector: {bank.bank_name} marked DOWN (outage spike detected)")
                bank.normal_windows_count = 0
            else:
                # Normal window
                bank.normal_windows_count += 1
                if bank.normal_windows_count >= 3 and bank.status == "DOWN":
                    bank.status = "UP"
                    bank.updated_at = now
                    print(f"BankOutageDetector: {bank.bank_name} marked UP (recovered after hysteresis)")
        
        db.commit()
    except Exception as e:
        print(f"Error in detect_bank_outages_job: {e}")
    finally:
        db.close()
