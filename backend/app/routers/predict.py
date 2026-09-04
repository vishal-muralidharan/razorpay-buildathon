from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.auth import verify_merchant
from app.liquidity_predictor import predict_liquidity_window

router = APIRouter(tags=["prediction"])


@router.get("/predict-retry-window/{customer_id}", response_model=schemas.PredictRetryWindowResponse)
def predict_retry_window(customer_id: int, merchant_name: str = Depends(verify_merchant), db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # The predictor now scores against a specific failed transaction (it
    # needs mandate/amount/subscription-age features for the ML model), so
    # this standalone-by-customer endpoint uses that customer's most recent
    # failed transaction as the scoring context. Also enforces merchant
    # scoping so one merchant can't probe another's customers.
    txn = (
        db.query(models.FailedTransaction)
        .join(models.Mandate)
        .filter(models.FailedTransaction.customer_id == customer_id)
        .filter(models.Mandate.merchant_name == merchant_name)
        .order_by(models.FailedTransaction.failed_at.desc())
        .first()
    )
    if not txn:
        raise HTTPException(
            status_code=404,
            detail="No failed transaction on file for this customer under your merchant account.",
        )

    recommended_date, confidence, method, sample_size, _shap_values = predict_liquidity_window(db, txn)

    return schemas.PredictRetryWindowResponse(
        customer_id=customer_id,
        recommended_date=recommended_date,
        confidence_score=confidence,
        method=method,
        sample_size=sample_size,
    )
