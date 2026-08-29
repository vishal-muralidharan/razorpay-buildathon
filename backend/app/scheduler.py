"""
Layer 2/4 - Dynamic Retry Budget Allocator + NPCI Compliance Gatekeeper.

Combined into one scheduler module per the MVP scope (the build brief
explicitly says to merge these two for the hackathon cut).

COMPLIANCE RULES IMPLEMENTED (mapped to NPCI's retry-limit requirements):
  1. MAX_RETRIES = 3 - NPCI permits at most 3 debit attempts per mandate
     per billing cycle. Any request for a 4th attempt is rejected at the
     API level (HTTP 400), and the transaction is marked EXHAUSTED.
  2. PEAK_HOURS_BLOCKED = 18:00-21:00 - retries are never scheduled in this
     window; a candidate slot that lands inside it is pushed to 21:00 the
     same day, which keeps the *date* the model predicted while respecting
     the no-peak-hour rule.
  3. Category-specific routing:
       - INSUFFICIENT_FUNDS -> never retried "now"; always routed to the
         liquidity window predictor for a data-driven future slot.
       - BANK_OUTAGE -> retried quickly (next non-peak hour) once the
         mock BankStatus table shows the bank is back UP; otherwise
         deferred by a short recheck interval.
       - MANDATE_EXPIRED / MANDATE_CANCELLED -> never auto-retried at all
         (no amount of retrying fixes a dead mandate) - routed instead to
         the re-mandate flow and the transaction is marked CANCELLED.
  4. Once a customer self-schedules a date (POST /customer-choose-date),
     automatic retries pause until that date - handled in the API layer,
     not here.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import models
from app.liquidity_predictor import predict_liquidity_window

MAX_RETRIES = 3
PEAK_HOUR_START = 18  # 6pm
PEAK_HOUR_END = 21    # 9pm
BANK_OUTAGE_RECHECK_HOURS = 4


def _push_out_of_peak_hours(slot: datetime) -> datetime:
    if PEAK_HOUR_START <= slot.hour < PEAK_HOUR_END:
        return slot.replace(hour=PEAK_HOUR_END, minute=0, second=0, microsecond=0)
    return slot


def decide_retry(db: Session, txn: models.FailedTransaction):
    """Core scheduling decision. Returns a dict describing the outcome,
    without writing to the DB - the router owns persistence + audit
    logging so every branch stays observable in one place."""

    if txn.retry_count >= MAX_RETRIES:
        return {
            "allowed": False,
            "scheduled_time": None,
            "predicted_success_prob": 0.0,
            "reason": (
                f"NPCI compliance cap reached: {txn.retry_count}/{MAX_RETRIES} attempts "
                "already used this billing cycle. No further retries permitted."
            ),
            "new_status": models.TransactionStatus.EXHAUSTED.value,
        }

    category = txn.decline_category

    if category == "MANDATE_EXPIRED" or category == "MANDATE_CANCELLED":
        return {
            "allowed": False,
            "scheduled_time": None,
            "predicted_success_prob": 0.0,
            "reason": (
                "Mandate is dead (expired/cancelled) - retrying the same mandate cannot "
                "succeed. Routed to the re-mandate flow instead of consuming a retry slot."
            ),
            "new_status": models.TransactionStatus.CANCELLED.value,
        }

    if category == "INSUFFICIENT_FUNDS":
        recommended_date, confidence, method, sample_size = predict_liquidity_window(
            db, txn.customer_id
        )
        slot = _push_out_of_peak_hours(recommended_date)
        return {
            "allowed": True,
            "scheduled_time": slot,
            "predicted_success_prob": confidence,
            "reason": (
                f"INSUFFICIENT_FUNDS - routed to predicted liquidity window instead of an "
                f"immediate retry. Model: {method} (n={sample_size}), predicted high-balance "
                f"day-of-month with confidence {confidence:.0%}."
            ),
            "new_status": models.TransactionStatus.SCHEDULED.value,
        }

    if category == "BANK_OUTAGE":
        bank_status = (
            db.query(models.BankStatus)
            .filter(models.BankStatus.bank_name == txn.mandate.bank_name)
            .first()
        )
        now = datetime.now(timezone.utc)
        if bank_status and bank_status.status == "UP":
            slot = _push_out_of_peak_hours(now + timedelta(minutes=30))
            return {
                "allowed": True,
                "scheduled_time": slot,
                "predicted_success_prob": 0.85,
                "reason": (
                    f"BANK_OUTAGE at {txn.mandate.bank_name} has cleared (status=UP) - "
                    "retrying promptly since the original failure was bank-side, not customer-side."
                ),
                "new_status": models.TransactionStatus.SCHEDULED.value,
            }
        else:
            slot = _push_out_of_peak_hours(now + timedelta(hours=BANK_OUTAGE_RECHECK_HOURS))
            return {
                "allowed": True,
                "scheduled_time": slot,
                "predicted_success_prob": 0.3,
                "reason": (
                    f"BANK_OUTAGE at {txn.mandate.bank_name} still ongoing (status=DOWN) - "
                    f"deferring retry by {BANK_OUTAGE_RECHECK_HOURS}h and rechecking bank status "
                    "rather than retrying blindly into a known outage."
                ),
                "new_status": models.TransactionStatus.SCHEDULED.value,
            }

    # UNKNOWN category - fall back to the liquidity predictor as a safe default
    recommended_date, confidence, method, sample_size = predict_liquidity_window(
        db, txn.customer_id
    )
    slot = _push_out_of_peak_hours(recommended_date)
    return {
        "allowed": True,
        "scheduled_time": slot,
        "predicted_success_prob": max(confidence - 0.15, 0.1),
        "reason": (
            "Decline category could not be classified with confidence - defaulting to the "
            "liquidity-window predictor as the safest general strategy."
        ),
        "new_status": models.TransactionStatus.SCHEDULED.value,
    }
