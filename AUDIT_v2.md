# Mandate Resurrection Agent - Codebase Audit v2

This document provides a comprehensive review of the current state of the codebase after the "Production Readiness Hardening" phase, identifying what has been resolved and what lingering inconsistencies, mock behaviors, and architectural gaps remain before this can safely handle real money in a production environment.

## 🟢 1. Addressed in Recent Updates

The following critical gaps identified in the v1 Audit have been successfully resolved:
- **ML & Data Pipeline**: Moved from hardcoded cohort logic to a calibrated XGBoost predictor with SHAP explainability.
- **Bank Outage Resilience**: Introduced a 5-minute rolling APScheduler job and a `/webhook/bank-status` endpoint to dynamically track downstream NPCI downtime.
- **Configurable Fallbacks**: Added a database-backed `MerchantRetryPolicy` to drop the hardcoded 3-day / 0.25 confidence heuristic in favor of merchant-specific configurations.
- **WhatsApp Templates**: Converted the `nudge.py` script to output strict Twilio Content SIDs and variables instead of business-initiated free-form strings.
- **Hash Chain Concurrency**: Validated that `with_for_update()` is in place for `FailedTransaction`, preventing race conditions when parallel webhooks update the audit ledger.
- **Testing**: Added a `pytest` suite ensuring the `decide_retry` engine obeys the 3-attempt NPCI compliance limits, peak hours, and hard decline filters.
- **Seeding Guardrails**: Removed DB seeding from `main.py` startup hooks and gated it behind an explicit `ENABLE_AUTO_SEED` environment variable in a standalone script.
- **Razorpay Sync**: Upgraded to token-based recurring debits and established a signed webhook listener.

---

## 🔴 2. Critical Inconsistencies (Action Required)

### A. Frontend Authentication Broken
While we successfully secured the backend endpoints (`/diagnose`, `/schedule-retry`, `/execute-retry`, `/transactions`) with `verify_merchant`, **the frontend (`api.js`) was not updated to pass the required `Authorization: Bearer <token>` header**.
- **Impact**: The UI dashboard is currently broken and will encounter `401 Unauthorized` or `403 Forbidden` responses when interacting with the secured backend.

### B. Dashboard Endpoint Data Leak
The `/dashboard/summary` and `/dashboard/live-feed` endpoints in `backend/app/routers/dashboard.py` do **not** use the `verify_merchant` dependency.
- **Impact**: Any merchant viewing the dashboard is currently pulling an aggregated view of `models.FailedTransaction.all()`. This is a severe multi-tenant data leak. The queries need to be strictly scoped to `txn.mandate.merchant_name == merchant_name`.

---

## 🟡 3. "Mocked" Pieces and Improvisations (Production Debt)

The following components are structurally complete but rely on mocked integrations or hardcoded data for the buildathon demo.

### A. Auth / Authz Identity Provider
- **Location**: `backend/app/auth.py`
- **Issue**: The `MOCK_MERCHANT_TOKENS` dictionary statically maps dummy strings (`secret-vela`) to merchant names. 
- **Fix**: Needs a real JWT validation layer connecting to a central Identity Provider (e.g. Auth0, Cognito) mapping OAuth scopes to Merchant IDs.

### B. ML Account Aggregator Pipeline
- **Location**: `backend/app/liquidity_predictor.py`
- **Issue**: `train_mock_model()` builds an XGBoost model in-memory on startup using the local SQLite synthetic data. 
- **Fix**: To get real balance signals, this requires an Account Aggregator TSP (Setu/Finvu) integration for consent-driven financial data. The model should be trained offline and loaded via a `.pkl` or `.onnx` artifact, not compiled at startup.

### C. Razorpay Tokens & Webhooks
- **Location**: `backend/scripts/seed_demo.py` & `backend/mock_webhook.py`
- **Issue**: The seed script generates synthetic `razorpay_customer_id` and `razorpay_token_id`. The webhook simulator pushes fake Razorpay payloads.
- **Fix**: The system assumes an upstream onboarding flow has successfully captured UPI Autopay / e-NACH mandates. To connect this, a webhook ingestion flow for mandate creation (`mandate.authorized`) must be built to populate the `Mandate` table with real tokens dynamically.

### D. Twilio Content SIDs
- **Location**: `backend/app/nudge.py`
- **Issue**: `CATEGORY_TEMPLATE_SIDS` uses fake template IDs (`HXabc123insufficient`).
- **Fix**: Real WhatsApp templates must be drafted, submitted to Meta for approval, and the resulting valid SIDs need to be mapped in production config.

### E. Scheduler Durability
- **Location**: `backend/app/scheduler_setup.py`
- **Issue**: While `APScheduler` is configured with `SQLAlchemyJobStore`, `main.py` simply starts and stops the scheduler locally.
- **Fix**: In a multi-node deployment, `APScheduler` works best backed by Redis (`RedisJobStore`) or Postgres to handle distributed locks correctly so jobs don't fire twice when multiple instances poll at the exact same second.
