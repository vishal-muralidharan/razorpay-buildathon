"""
ORM models.

Core tables requested in the build brief:
  - Mandate
  - FailedTransaction
  - RetryDecision
  - AuditLog

Supporting tables added to make those four actually work end to end:
  - Customer            (who the mandate belongs to; needed for nudges + liquidity prediction)
  - DebitHistory         (past successful debit dates -> feeds the liquidity window predictor)
  - BankStatus            (mock bank-outage flag the scheduler checks)
  - NudgeLog              (WhatsApp/SMS messages sent, and the customer's self-scheduled date)
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Enum, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


class DeclineCategory(str, enum.Enum):
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    BANK_OUTAGE = "BANK_OUTAGE"
    MANDATE_EXPIRED = "MANDATE_EXPIRED"
    MANDATE_CANCELLED = "MANDATE_CANCELLED"
    UNKNOWN = "UNKNOWN"


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"           # awaiting diagnosis/scheduling
    SCHEDULED = "SCHEDULED"       # retry slot chosen, waiting for it to arrive
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION" # API initiated, awaiting webhook
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"  # customer self-scheduling, auto-retry paused
    RECOVERED = "RECOVERED"       # retry succeeded, revenue recovered
    EXHAUSTED = "EXHAUSTED"       # 3 NPCI-permitted attempts used, still failing
    CANCELLED = "CANCELLED"       # mandate cancelled / customer opted out


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    preferred_language = Column(String, default="hi-en")  # e.g. Hinglish

    mandates = relationship("Mandate", back_populates="customer")
    debit_history = relationship("DebitHistory", back_populates="customer")


class Mandate(Base):
    __tablename__ = "mandates"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    frequency = Column(String, default="MONTHLY")  # MONTHLY, QUARTERLY, etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="ACTIVE")  # ACTIVE, EXPIRED, CANCELLED
    subscription_age_days = Column(Integer, default=0)
    merchant_name = Column(String, default="Vela SaaS")
    bank_name = Column(String, default="HDFC")
    razorpay_customer_id = Column(String, nullable=True)
    razorpay_token_id = Column(String, nullable=True)

    customer = relationship("Customer", back_populates="mandates")
    transactions = relationship("FailedTransaction", back_populates="mandate")


class DebitHistory(Base):
    """Past successful debits for a customer - the raw signal the liquidity
    predictor uses to learn each customer's high-balance window."""
    __tablename__ = "debit_history"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    debit_date = Column(DateTime(timezone=True), nullable=False)
    day_of_month = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)

    customer = relationship("Customer", back_populates="debit_history")


class BankStatus(Base):
    """Mock uptime table. Seeded manually for the demo; a Bank Server Uptime
    Tracker in a real deployment would write to this table from a live feed."""
    __tablename__ = "bank_status"

    id = Column(Integer, primary_key=True, index=True)
    bank_name = Column(String, unique=True, nullable=False)
    status = Column(String, default="UP")  # UP or DOWN
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    normal_windows_count = Column(Integer, default=3)


class MerchantRetryPolicy(Base):
    """Configurable fallback values for liquidity prediction per merchant."""
    __tablename__ = "merchant_retry_policy"

    id = Column(Integer, primary_key=True, index=True)
    merchant_name = Column(String, unique=True, nullable=False)
    fallback_days = Column(Integer, default=3)
    fallback_confidence = Column(Float, default=0.25)


class FailedTransaction(Base):
    __tablename__ = "failed_transactions"

    id = Column(Integer, primary_key=True, index=True)
    mandate_id = Column(Integer, ForeignKey("mandates.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    decline_code = Column(String, nullable=False)
    decline_category = Column(String, default=DeclineCategory.UNKNOWN.value)
    failed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    retry_count = Column(Integer, default=0)  # attempts consumed of the NPCI cap of 3
    status = Column(String, default=TransactionStatus.PENDING.value)
    customer_chosen_date = Column(DateTime(timezone=True), nullable=True)
    recovered_at = Column(DateTime(timezone=True), nullable=True)

    mandate = relationship("Mandate", back_populates="transactions")
    decisions = relationship("RetryDecision", back_populates="transaction")
    audit_logs = relationship("AuditLog", back_populates="transaction")
    nudges = relationship("NudgeLog", back_populates="transaction")


class RetryDecision(Base):
    __tablename__ = "retry_decisions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("failed_transactions.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)  # 1, 2, or 3
    chosen_slot_time = Column(DateTime(timezone=True), nullable=False)
    predicted_success_prob = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    outcome = Column(String, default="PENDING")  # PENDING, SUCCESS, FAILURE

    transaction = relationship("FailedTransaction", back_populates="decisions")


class NudgeLog(Base):
    __tablename__ = "nudge_logs"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("failed_transactions.id"), nullable=False)
    channel = Column(String, default="whatsapp")  # whatsapp or sms
    message = Column(Text, nullable=False)
    self_schedule_options = Column(Text, nullable=True)  # JSON list of 3 candidate dates
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    simulated = Column(Boolean, default=True)

    transaction = relationship("FailedTransaction", back_populates="nudges")


class AuditLog(Base):
    """Append-only, hash-chained audit trail. Each row's `hash` covers
    prev_hash + this row's own fields, so any edit to an earlier row breaks
    every hash after it - a tamper-evident ledger without real blockchain infra."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("failed_transactions.id"), nullable=False)
    step_name = Column(String, nullable=False)
    payload_json = Column(JSON, nullable=False)
    prev_hash = Column(String, nullable=False)
    hash = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    transaction = relationship("FailedTransaction", back_populates="audit_logs")
