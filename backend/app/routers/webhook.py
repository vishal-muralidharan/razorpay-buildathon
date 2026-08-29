import hmac
import hashlib
import os
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, audit
from app.scheduler import MAX_RETRIES

router = APIRouter(tags=["webhooks"])

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret:
        # Pass-through for local demo simulation
        return True
    expected_mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_mac, signature)

@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives asynchronous callbacks from Razorpay when a recurring payment succeeds or fails."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    
    if RAZORPAY_WEBHOOK_SECRET and not verify_signature(body, signature, RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("event")
    
    # We pass transaction_id and decision_id in the 'notes' field during the API charge call
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    notes = payment_entity.get("notes", {})
    
    transaction_id = notes.get("transaction_id")
    decision_id = notes.get("decision_id")
    
    if not transaction_id or not decision_id:
        return {"status": "ignored", "reason": "Missing tracking notes"}
        
    # Serialize updates by locking the parent transaction row
    txn = db.query(models.FailedTransaction).filter_by(id=transaction_id).with_for_update().first()
    if not txn:
        return {"status": "not_found"}
        
    decision = db.query(models.RetryDecision).get(decision_id)
    if not decision:
        return {"status": "not_found"}
        
    if decision.outcome != "PENDING":
        return {"status": "already_processed"}

    if event == "payment.captured":
        decision.outcome = "SUCCESS"
        txn.status = models.TransactionStatus.RECOVERED.value
        txn.recovered_at = datetime.now(timezone.utc)
        
        audit.log_step(db, txn.id, "WEBHOOK_PAYMENT_CAPTURED", {
            "attempt_number": decision.attempt_number,
            "razorpay_payment_id": payment_entity.get("id"),
            "event": event
        })
        
    elif event == "payment.failed":
        decision.outcome = "FAILURE"
        txn.status = (
            models.TransactionStatus.EXHAUSTED.value
            if txn.retry_count >= MAX_RETRIES
            else models.TransactionStatus.PENDING.value
        )
        
        audit.log_step(db, txn.id, "WEBHOOK_PAYMENT_FAILED", {
            "attempt_number": decision.attempt_number,
            "razorpay_payment_id": payment_entity.get("id"),
            "error_description": payment_entity.get("error_description"),
            "event": event
        })
    else:
        return {"status": "ignored", "reason": f"Unhandled event {event}"}
        
    db.commit()
    return {"status": "ok"}
