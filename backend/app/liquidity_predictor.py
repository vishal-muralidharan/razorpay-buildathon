"""
Layer 2 - Salary & Liquidity Window Estimator (the ML core).

MODELING CHOICE: a day-of-month frequency histogram, not a trained
classifier. Rationale, for the README and for judges:

  1. Low data per customer. A subscription that bills monthly produces at
     most ~12 successful-debit data points a year. That is nowhere near
     enough to fit a supervised model per customer without massive
     overfitting risk.
  2. Explainability matters more than marginal accuracy here. The output
     feeds a compliance-constrained decision (you only get 3 NPCI retries),
     so "we picked the 7th because you were paid successfully on the 6th,
     7th, and 8th three months running" is a trustworthy, auditable reason.
     A gradient-boosted black box is not, for the same data volume.
  3. Salaries and recurring inflows are strongly periodic by day-of-month
     (salary day, EMI-clear day), so day-of-month is a strong, cheap
     feature - most of the achievable signal for little modeling cost.

ALGORITHM:
  - Pull the customer's DebitHistory (successful past debits).
  - Build a histogram of day-of-month across those debits.
  - recommended_date = the next calendar occurrence of the most frequent
    day-of-month, confidence = (count of that day) / (total debits).
  - COLD-START FALLBACK: if a customer has fewer than MIN_HISTORY_FOR_PERSONAL
    successful debits on file, fall back to a cohort-level histogram built
    across all customers, with a lower confidence score to reflect the
    weaker, population-level signal.

This is deliberately swappable: a future iteration could replace
`_customer_histogram` with a trained model (e.g. gradient boosting on
salary-cycle features) behind the same function signature without touching
any caller.
"""
from collections import Counter
from datetime import datetime, timedelta
import calendar

from sqlalchemy.orm import Session

from app import models

MIN_HISTORY_FOR_PERSONAL = 3


def _next_occurrence_of_day(day_of_month: int, after: datetime) -> datetime:
    """Return the next calendar date (at 10:00, a safely non-peak hour) that
    falls on `day_of_month`, strictly after `after`."""
    year, month = after.year, after.month
    for _ in range(3):  # look ahead up to 3 months in case day doesn't exist (e.g. 31st)
        last_day = calendar.monthrange(year, month)[1]
        candidate_day = min(day_of_month, last_day)
        candidate = datetime(year, month, candidate_day, 10, 0, 0)
        if candidate > after:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    # fallback: a week out
    return after + timedelta(days=7)


def predict_liquidity_window(db: Session, customer_id: int, after: datetime = None):
    """Returns (recommended_date, confidence_score, method, sample_size)."""
    after = after or datetime.utcnow()

    personal_history = (
        db.query(models.DebitHistory)
        .filter(models.DebitHistory.customer_id == customer_id)
        .all()
    )

    if len(personal_history) >= MIN_HISTORY_FOR_PERSONAL:
        days = [d.day_of_month for d in personal_history]
        counts = Counter(days)
        best_day, best_count = counts.most_common(1)[0]
        confidence = round(best_count / len(days), 3)
        recommended_date = _next_occurrence_of_day(best_day, after)
        return recommended_date, confidence, "personal_histogram", len(days)

    # Cold-start: cohort-level fallback across all customers' history
    all_history = db.query(models.DebitHistory).all()
    if all_history:
        days = [d.day_of_month for d in all_history]
        counts = Counter(days)
        best_day, best_count = counts.most_common(1)[0]
        # cohort signal is weaker per-customer -> discount the confidence
        raw_confidence = best_count / len(days)
        confidence = round(min(raw_confidence, 0.5), 3)
        recommended_date = _next_occurrence_of_day(best_day, after)
        return recommended_date, confidence, "cohort_fallback", len(all_history)

    # No data anywhere yet: default to "retry in 3 days", low confidence
    return after + timedelta(days=3), 0.25, "default_no_data", 0
