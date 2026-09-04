import pytest
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.scheduler import decide_retry, MAX_RETRIES
from app.models import FailedTransaction, Mandate, TransactionStatus

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_txn():
    txn = FailedTransaction(
        id=1,
        decline_category="INSUFFICIENT_FUNDS",
        retry_count=0,
        status=TransactionStatus.PENDING.value,
        failed_at=datetime.now(timezone.utc),
    )
    txn.mandate = Mandate(bank_name="HDFC", merchant_name="Test Merchant")
    return txn


@pytest.mark.parametrize("retry_count,expected_allowed,expected_status", [
    (0, True, TransactionStatus.SCHEDULED.value),
    (1, True, TransactionStatus.SCHEDULED.value),
    (2, True, TransactionStatus.SCHEDULED.value),
    (MAX_RETRIES, False, TransactionStatus.EXHAUSTED.value),
])
@patch("app.scheduler.predict_liquidity_window")
def test_retry_exhaustion(mock_predict, mock_db, mock_txn, retry_count, expected_allowed, expected_status):
    mock_txn.retry_count = retry_count
    mock_txn.decline_category = "INSUFFICIENT_FUNDS"
    
    mock_predict.return_value = (datetime.now(timezone.utc), 0.8, "test", 100, None)
    
    decision = decide_retry(mock_db, mock_txn)
    assert decision["allowed"] == expected_allowed
    assert decision["new_status"] == expected_status


@patch("app.scheduler.predict_liquidity_window")
def test_bank_outage_down(mock_predict, mock_db, mock_txn):
    mock_txn.decline_category = "BANK_OUTAGE"
    # Mock bank status query
    mock_status = MagicMock()
    mock_status.status = "DOWN"
    mock_db.query().filter().first.return_value = mock_status
    
    decision = decide_retry(mock_db, mock_txn)
    assert decision["allowed"] is True
    assert "BANK_OUTAGE" in decision["reason"]
    # Should defer by hours, not use ML liquidity predictor
    mock_predict.assert_not_called()


@patch("app.scheduler.predict_liquidity_window")
def test_bank_outage_up(mock_predict, mock_db, mock_txn):
    mock_txn.decline_category = "BANK_OUTAGE"
    mock_status = MagicMock()
    mock_status.status = "UP"
    mock_db.query().filter().first.return_value = mock_status
    
    # If bank is UP, it delegates back to INSUFFICIENT_FUNDS handling
    mock_predict.return_value = (datetime.now(timezone.utc), 0.8, "test", 100, None)
    
    decision = decide_retry(mock_db, mock_txn)
    assert decision["allowed"] is True
    assert "cleared" in decision["reason"]
    mock_predict.assert_not_called()


def test_hard_decline(mock_db, mock_txn):
    for category in ["MANDATE_EXPIRED", "MANDATE_CANCELLED"]:
        mock_txn.decline_category = category
        decision = decide_retry(mock_db, mock_txn)
        assert decision["allowed"] is False
        assert decision["new_status"] == "CANCELLED"
