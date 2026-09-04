from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class DiagnoseRequest(BaseModel):
    transaction_id: int


class DiagnoseResponse(BaseModel):
    transaction_id: int
    decline_code: str
    category: str
    explanation: str


class PredictRetryWindowResponse(BaseModel):
    customer_id: int
    recommended_date: datetime
    confidence_score: float
    method: str
    sample_size: int


class ScheduleRetryRequest(BaseModel):
    transaction_id: int


class ScheduleRetryResponse(BaseModel):
    transaction_id: int
    scheduled_time: Optional[datetime]
    attempts_used: int
    attempts_remaining: int
    reason: str
    status: str


class CustomerChooseDateRequest(BaseModel):
    transaction_id: int
    chosen_date: datetime
    token: str


class CustomerChooseDateResponse(BaseModel):
    transaction_id: int
    status: str
    chosen_date: datetime
    message: str


class ExecuteRetryRequest(BaseModel):
    transaction_id: int


class ExecuteRetryResponse(BaseModel):
    transaction_id: int
    outcome: str
    razorpay_payment_id: Optional[str]
    status: str
    attempts_used: int


class AuditLogEntry(BaseModel):
    id: int
    step_name: str
    payload_json: str
    prev_hash: str
    hash: str
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditTrailResponse(BaseModel):
    transaction_id: int
    chain_valid: bool
    entries: List[AuditLogEntry]


class TransactionSummary(BaseModel):
    id: int
    customer_name: str
    amount: float
    decline_code: str
    decline_category: str
    status: str
    retry_count: int
    failed_at: datetime

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    total_at_risk: float
    total_recovered: float
    recovery_rate_pct: float
    total_transactions: int
    recovered_count: int
    exhausted_count: int
    pending_count: int
    api_calls_saved_estimate: int
    by_category: dict
