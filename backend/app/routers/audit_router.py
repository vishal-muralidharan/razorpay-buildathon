from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.audit import verify_chain
from app.auth import verify_merchant

router = APIRouter(tags=["audit"])


@router.get("/audit/{transaction_id}", response_model=schemas.AuditTrailResponse)
def get_audit_trail(transaction_id: int, merchant_name: str = Depends(verify_merchant), db: Session = Depends(get_db)):
    txn = db.query(models.FailedTransaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.mandate.merchant_name != merchant_name:
        raise HTTPException(status_code=403, detail="Unauthorized for this transaction")

    entries = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.transaction_id == transaction_id)
        .order_by(models.AuditLog.id.asc())
        .all()
    )

    return schemas.AuditTrailResponse(
        transaction_id=transaction_id,
        chain_valid=verify_chain(entries),
        entries=entries,
    )
