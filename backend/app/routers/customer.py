from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, audit
from app.database import get_db
from app.auth import verify_customer_token

router = APIRouter(tags=["customer"])

@router.post("/customer-choose-date", response_model=schemas.CustomerChooseDateResponse)
def customer_choose_date(req: schemas.CustomerChooseDateRequest, db: Session = Depends(get_db)):
    # Verify the customer's short-lived JWT token
    token_txn_id = verify_customer_token(req.token)
    
    if token_txn_id != req.transaction_id:
        raise HTTPException(status_code=403, detail="Token does not match the requested transaction")

    txn = db.query(models.FailedTransaction).get(req.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.customer_chosen_date = req.chosen_date
    txn.status = models.TransactionStatus.AWAITING_CUSTOMER.value
    db.commit()

    audit.log_step(db, txn.id, "CUSTOMER_SELF_SCHEDULED", {
        "chosen_date": req.chosen_date,
        "effect": "Automated retry scheduling paused until this date.",
    })

    return schemas.CustomerChooseDateResponse(
        transaction_id=txn.id,
        status=txn.status,
        chosen_date=req.chosen_date,
        message="Got it - we've paused automatic retries and will attempt your payment on the date you picked.",
    )
