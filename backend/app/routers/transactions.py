from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=list[schemas.TransactionSummary])
def list_transactions(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(models.FailedTransaction)
    if status:
        q = q.filter(models.FailedTransaction.status == status)
    if category:
        q = q.filter(models.FailedTransaction.decline_category == category)
    txns = q.order_by(models.FailedTransaction.failed_at.desc()).limit(limit).all()

    return [
        schemas.TransactionSummary(
            id=t.id,
            customer_name=t.mandate.customer.name,
            amount=t.amount,
            decline_code=t.decline_code,
            decline_category=t.decline_category,
            status=t.status,
            retry_count=t.retry_count,
            failed_at=t.failed_at,
        )
        for t in txns
    ]


@router.get("/transactions/{transaction_id}")
def get_transaction_detail(transaction_id: int, db: Session = Depends(get_db)):
    t = db.query(models.FailedTransaction).get(transaction_id)
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "id": t.id,
        "customer": {"id": t.customer_id, "name": t.mandate.customer.name, "phone": t.mandate.customer.phone},
        "mandate": {
            "id": t.mandate_id,
            "merchant_name": t.mandate.merchant_name,
            "bank_name": t.mandate.bank_name,
            "amount": t.mandate.amount,
            "frequency": t.mandate.frequency,
            "subscription_age_days": t.mandate.subscription_age_days,
        },
        "amount": t.amount,
        "decline_code": t.decline_code,
        "decline_category": t.decline_category,
        "status": t.status,
        "retry_count": t.retry_count,
        "failed_at": t.failed_at,
        "recovered_at": t.recovered_at,
        "customer_chosen_date": t.customer_chosen_date,
        "decisions": [
            {
                "attempt_number": d.attempt_number,
                "chosen_slot_time": d.chosen_slot_time,
                "predicted_success_prob": d.predicted_success_prob,
                "reason": d.reason,
                "outcome": d.outcome,
            }
            for d in sorted(t.decisions, key=lambda d: d.attempt_number)
        ],
        "nudges": [
            {
                "channel": n.channel,
                "message": n.message,
                "sent_at": n.sent_at,
                "simulated": n.simulated,
            }
            for n in t.nudges
        ],
    }
