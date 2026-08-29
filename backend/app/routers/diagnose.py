from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, audit
from app.database import get_db
from app.decline_parser import parse_decline_code

from app.auth import verify_merchant

router = APIRouter(tags=["diagnosis"])


@router.post("/diagnose", response_model=schemas.DiagnoseResponse)
def diagnose(req: schemas.DiagnoseRequest, merchant_name: str = Depends(verify_merchant), db: Session = Depends(get_db)):
    txn = db.query(models.FailedTransaction).get(req.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.mandate.merchant_name != merchant_name:
        raise HTTPException(status_code=403, detail="Unauthorized for this transaction")

    category, explanation = parse_decline_code(txn.decline_code)
    txn.decline_category = category
    db.commit()

    audit.log_step(db, txn.id, "DIAGNOSIS", {
        "decline_code": txn.decline_code,
        "category": category,
        "explanation": explanation,
    })

    return schemas.DiagnoseResponse(
        transaction_id=txn.id,
        decline_code=txn.decline_code,
        category=category,
        explanation=explanation,
    )
