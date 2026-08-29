from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.audit import verify_chain

router = APIRouter(tags=["audit"])


@router.get("/audit/{transaction_id}", response_model=schemas.AuditTrailResponse)
def get_audit_trail(transaction_id: int, db: Session = Depends(get_db)):
    txn = db.query(models.FailedTransaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

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
