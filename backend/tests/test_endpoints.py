"""
Endpoint-level tests using FastAPI's TestClient against a real database
(whatever DATABASE_URL the environment already configures - defaults to the
same local SQLite file as `uvicorn app.main:app`), seeded with the same
scripts.seed_demo data used for the manual demo.

Why this file exists: the pre-existing test_scheduler.py mocks
predict_liquidity_window() entirely, so it never notices when a router
passes the wrong arguments into it. These tests call the actual HTTP
endpoints end to end, so a signature mismatch, a missing auth dependency,
or a route that 500s shows up here instead of only in production.

Note: this deliberately does NOT set os.environ["DATABASE_URL"] itself -
app.database binds its engine to that variable at import time, and by the
time this file's fixture runs, app.database may already have been imported
(and its engine created) by another test module in the same pytest
session, so setting the env var here would have no effect. Instead it
works with whatever engine the app already has, resetting the schema
before each test run.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENABLE_AUTO_SEED", "true")


@pytest.fixture(scope="module")
def client():
    from app.database import Base, engine, SessionLocal
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from scripts.seed_demo import run_seed
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()

    from app.main import app
    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)


AUTH = {"Authorization": "Bearer secret-vela"}


def _first_vela_transaction(client, category=None):
    params = {"category": category} if category else {}
    resp = client.get("/transactions", headers=AUTH, params=params)
    assert resp.status_code == 200
    txns = resp.json()
    assert txns, f"expected at least one seeded transaction for category={category}"
    return txns[0]["id"]


def test_predict_retry_window_returns_200_not_500(client):
    """Regression test for the predict.py / predict_liquidity_window
    signature mismatch that made this endpoint 500 on every call."""
    txn_id = _first_vela_transaction(client, category="INSUFFICIENT_FUNDS")
    customer_id = client.get(f"/transactions/{txn_id}", headers=AUTH).json()["customer"]["id"]

    resp = client.get(f"/predict-retry-window/{customer_id}", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert "recommended_date" in body
    assert 0.0 <= body["confidence_score"] <= 1.0


@pytest.mark.parametrize("path,method", [
    ("/audit/1", "get"),
    ("/predict-retry-window/1", "get"),
])
def test_previously_unauthenticated_endpoints_require_auth(client, path, method):
    """Regression test: /audit and /predict-retry-window used to skip
    verify_merchant entirely, leaking any merchant's data to anyone."""
    resp = getattr(client, method)(path)
    assert resp.status_code == 401


def test_customer_choose_date_requires_auth(client):
    resp = client.post("/customer-choose-date", json={
        "transaction_id": 1, "chosen_date": "2026-09-15T10:00:00Z",
    })
    assert resp.status_code == 401


def test_full_schedule_execute_flow_resolves_outcome(client):
    """Regression test: simulated executions used to get stuck in
    PENDING_CONFIRMATION forever because nothing ever called the webhook
    that only a real Razorpay integration would trigger."""
    txn_id = _first_vela_transaction(client, category="INSUFFICIENT_FUNDS")

    diag = client.post("/diagnose", headers=AUTH, json={"transaction_id": txn_id})
    assert diag.status_code == 200

    sched = client.post("/schedule-retry", headers=AUTH, json={"transaction_id": txn_id})
    assert sched.status_code == 200
    assert sched.json()["status"] == "SCHEDULED"

    exe = client.post("/execute-retry", headers=AUTH, json={"transaction_id": txn_id})
    assert exe.status_code == 200
    assert exe.json()["outcome"] in ("SUCCESS", "FAILURE"), (
        "simulated execution must resolve immediately, not stay PENDING"
    )

    detail = client.get(f"/transactions/{txn_id}", headers=AUTH).json()
    assert detail["nudges"], "expected a nudge to have been logged"
    message = detail["nudges"][0]["message"]
    assert message.startswith("Hi "), (
        f"nudge message should be a readable sentence, got: {message!r}"
    )


def test_compliance_cap_rejects_fourth_attempt(client):
    txn_id = _first_vela_transaction(client, category="BANK_OUTAGE")
    client.post("/diagnose", headers=AUTH, json={"transaction_id": txn_id})

    for _ in range(3):
        sched = client.post("/schedule-retry", headers=AUTH, json={"transaction_id": txn_id})
        assert sched.status_code == 200
        client.post("/execute-retry", headers=AUTH, json={"transaction_id": txn_id})

    rejected = client.post("/schedule-retry", headers=AUTH, json={"transaction_id": txn_id})
    assert rejected.status_code == 400
