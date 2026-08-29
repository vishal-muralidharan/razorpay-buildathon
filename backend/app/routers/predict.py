from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.liquidity_predictor import predict_liquidity_window

router = APIRouter(tags=["prediction"])


@router.get("/predict-retry-window/{customer_id}", response_model=schemas.PredictRetryWindowResponse)
def predict_retry_window(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    recommended_date, confidence, method, sample_size = predict_liquidity_window(db, customer_id)

    return schemas.PredictRetryWindowResponse(
        customer_id=customer_id,
        recommended_date=recommended_date,
        confidence_score=confidence,
        method=method,
        sample_size=sample_size,
    )
