"""
Layer 2 - Salary & Liquidity Window Estimator (the ML core).
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import calendar
import random
import numpy as np
import pandas as pd

from sqlalchemy.orm import Session
from app import models

try:
    import xgboost as xgb
    from sklearn.calibration import CalibratedClassifierCV
    import shap
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

MIN_HISTORY_FOR_PERSONAL = 3

# Global state for our mock model
_ml_model = None
_shap_explainer = None


def train_mock_model():
    """Builds and trains a mock XGBoost model on synthetic Account Aggregator features.
    
    TODO (Account Aggregator Integration):
    Get real balance signals via an Account Aggregator integration (Setu/Finvu).
    This requires a separate consent-flow/compliance project, scoped separately.
    Once real data exists, we should train offline and load a versioned model 
    artifact (.pkl/.onnx) at startup instead of training dynamically on synthetic data.
    """
    global _ml_model, _shap_explainer
    if not ML_AVAILABLE:
        print("ML libraries not installed. Skipping model training.")
        return

    print("Training mock calibrated XGBoost model...")
    # Generate synthetic training data
    np.random.seed(42)
    n_samples = 1000
    
    # Features: day_of_month, days_of_history_available, amount, subscription_age_days
    X_train = pd.DataFrame({
        "day_of_month": np.random.randint(1, 29, n_samples),
        "days_of_history_available": np.random.randint(0, 365, n_samples),
        "amount": np.random.uniform(100, 5000, n_samples),
        "subscription_age_days": np.random.randint(0, 700, n_samples),
        "balance_trend": np.random.uniform(-1, 1, n_samples)
    })
    
    # Make success more likely around typical salary days (1st-5th and 25th-28th)
    def synth_target(row):
        prob = 0.2
        if 1 <= row["day_of_month"] <= 5 or 25 <= row["day_of_month"] <= 28:
            prob += 0.5
        if row["balance_trend"] > 0:
            prob += 0.2
        return np.random.random() < min(prob, 0.95)
        
    y_train = X_train.apply(synth_target, axis=1)

    base_xgb = xgb.XGBClassifier(
        n_estimators=50, 
        max_depth=3, 
        learning_rate=0.1, 
        objective="binary:logistic"
    )
    
    # Calibrate probabilities using Isotonic Regression
    _ml_model = CalibratedClassifierCV(base_xgb, method="isotonic", cv=3)
    _ml_model.fit(X_train, y_train)
    
    # Train SHAP explainer on the underlying XGB estimators
    # (Since CalibratedClassifierCV wraps multiple models, we just explain one for demo)
    _shap_explainer = shap.TreeExplainer(_ml_model.calibrated_classifiers_[0].estimator)
    print("Model trained and calibrated successfully.")


def _next_occurrence_of_day(day_of_month: int, after: datetime) -> datetime:
    year, month = after.year, after.month
    for _ in range(3):
        last_day = calendar.monthrange(year, month)[1]
        candidate_day = min(day_of_month, last_day)
        candidate = datetime(year, month, candidate_day, 10, 0, 0, tzinfo=timezone.utc)
        if candidate > after:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    return after + timedelta(days=7)


def _extract_features(txn: models.FailedTransaction, candidate_date: datetime, history_count: int) -> pd.DataFrame:
    # Dummy mock feature extraction that would normally hit AA API
    return pd.DataFrame({
        "day_of_month": [candidate_date.day],
        "days_of_history_available": [history_count * 30],
        "amount": [txn.amount],
        "subscription_age_days": [txn.mandate.subscription_age_days],
        "balance_trend": [random.uniform(-0.5, 0.8)]
    })


def predict_liquidity_window(db: Session, txn: models.FailedTransaction, after: datetime = None):
    """Returns (recommended_date, confidence_score, method, sample_size, shap_values)."""
    after = after or datetime.now(timezone.utc)
    
    personal_history = (
        db.query(models.DebitHistory)
        .filter(models.DebitHistory.customer_id == txn.customer_id)
        .all()
    )

    # 1. Attempt ML Model Inference
    if _ml_model is not None and _shap_explainer is not None:
        try:
            best_date = None
            best_prob = -1
            best_features = None
            
            # Score the next 14 days
            for offset in range(1, 15):
                candidate = after + timedelta(days=offset)
                candidate = candidate.replace(hour=10, minute=0, second=0, microsecond=0)
                
                features = _extract_features(txn, candidate, len(personal_history))
                prob = _ml_model.predict_proba(features)[0][1]
                
                if prob > best_prob:
                    best_prob = prob
                    best_date = candidate
                    best_features = features
            
            # Generate SHAP values for the best candidate
            shap_vals = _shap_explainer.shap_values(best_features)[0]
            feature_names = best_features.columns
            shap_dict = {str(name): float(val) for name, val in zip(feature_names, shap_vals)}
            
            return best_date, float(best_prob), "xgboost_calibrated", len(personal_history), shap_dict
        except Exception as e:
            print(f"ML Model inference failed: {e}. Falling back to heuristic.")

    # 2. Fallback: Personal Histogram
    if len(personal_history) >= MIN_HISTORY_FOR_PERSONAL:
        days = [d.day_of_month for d in personal_history]
        counts = Counter(days)
        best_day, best_count = counts.most_common(1)[0]
        confidence = round(best_count / len(days), 3)
        recommended_date = _next_occurrence_of_day(best_day, after)
        return recommended_date, confidence, "personal_histogram", len(days), None

    # 3. Fallback: Cohort Histogram
    all_history = db.query(models.DebitHistory).all()
    if all_history:
        days = [d.day_of_month for d in all_history]
        counts = Counter(days)
        best_day, best_count = counts.most_common(1)[0]
        raw_confidence = best_count / len(days)
        confidence = round(min(raw_confidence, 0.5), 3)
        recommended_date = _next_occurrence_of_day(best_day, after)
        return recommended_date, confidence, "cohort_fallback", len(all_history), None

    # 4. Fallback: No data anywhere, use merchant policy or defaults
    policy = db.query(models.MerchantRetryPolicy).filter_by(merchant_name=txn.mandate.merchant_name).first()
    fallback_days = policy.fallback_days if policy else 3
    fallback_conf = policy.fallback_confidence if policy else 0.25
    return after + timedelta(days=fallback_days), fallback_conf, "default_no_data", 0, None
