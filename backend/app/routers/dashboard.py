from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.auth import verify_merchant

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=schemas.DashboardSummary)
def dashboard_summary(merchant_name: str = Depends(verify_merchant), db: Session = Depends(get_db)):
    txns = db.query(models.FailedTransaction).join(models.Mandate).filter(models.Mandate.merchant_name == merchant_name).all()

    total_at_risk = sum(t.amount for t in txns if t.status != models.TransactionStatus.RECOVERED.value)
    total_recovered = sum(t.amount for t in txns if t.status == models.TransactionStatus.RECOVERED.value)
    recovered_count = sum(1 for t in txns if t.status == models.TransactionStatus.RECOVERED.value)
    exhausted_count = sum(1 for t in txns if t.status == models.TransactionStatus.EXHAUSTED.value)
    pending_count = sum(
        1 for t in txns
        if t.status in (
            models.TransactionStatus.PENDING.value,
            models.TransactionStatus.SCHEDULED.value,
            models.TransactionStatus.AWAITING_CUSTOMER.value,
            models.TransactionStatus.PENDING_CONFIRMATION.value,
        )
    )
    total = len(txns)
    recovery_rate = round((recovered_count / total) * 100, 1) if total else 0.0

    # Naive but honest ROI proxy: every transaction the model routed to a
    # predicted window / bank-recheck instead of an immediate blind retry
    # is one fewer wasted API call against the 3-attempt NPCI budget.
    api_calls_saved = sum(1 for t in txns if t.decline_category == "INSUFFICIENT_FUNDS" and t.retry_count <= 1)

    by_category = {}
    for t in txns:
        by_category.setdefault(t.decline_category, {"count": 0, "amount": 0.0})
        by_category[t.decline_category]["count"] += 1
        by_category[t.decline_category]["amount"] += t.amount

    return schemas.DashboardSummary(
        total_at_risk=round(total_at_risk, 2),
        total_recovered=round(total_recovered, 2),
        recovery_rate_pct=recovery_rate,
        total_transactions=total,
        recovered_count=recovered_count,
        exhausted_count=exhausted_count,
        pending_count=pending_count,
        api_calls_saved_estimate=api_calls_saved,
        by_category=by_category,
    )


@router.get("/live-feed")
def live_feed(limit: int = 20, merchant_name: str = Depends(verify_merchant), db: Session = Depends(get_db)):
    decisions = (
        db.query(models.RetryDecision)
        .join(models.FailedTransaction, models.RetryDecision.transaction_id == models.FailedTransaction.id)
        .join(models.Mandate, models.FailedTransaction.mandate_id == models.Mandate.id)
        .filter(models.Mandate.merchant_name == merchant_name)
        .order_by(models.RetryDecision.id.desc())
        .limit(limit)
        .all()
    )
    feed = []
    for d in decisions:
        txn = d.transaction
        feed.append({
            "transaction_id": txn.id,
            "customer_name": txn.mandate.customer.name if txn.mandate else None,
            "decline_code": txn.decline_code,
            "decline_category": txn.decline_category,
            "predicted_window": d.chosen_slot_time,
            "predicted_success_prob": d.predicted_success_prob,
            "outcome": d.outcome,
            "reason": d.reason,
            "decided_at": d.created_at,
        })
    return feed
