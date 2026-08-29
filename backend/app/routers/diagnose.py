from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, audit
from app.database import get_db
from app.decline_parser import parse_decline_code

router = APIRouter(tags=["diagnosis"])


@router.post("/diagnose", response_model=schemas.DiagnoseResponse)
def diagnose(req: schemas.DiagnoseRequest, db: Session = Depends(get_db)):
    txn = db.query(models.FailedTransaction).get(req.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

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
