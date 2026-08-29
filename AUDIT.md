# Codebase Audit: Mandate Resurrection Agent

This document provides a detailed audit of the entire codebase, listing all API endpoints, functionalities that need to be implemented for a production deployment, and current inconsistencies or placeholder logic (mocks/simulations).

## 1. API Endpoints

The backend is built with FastAPI and is divided into several routers. Below is the complete list of endpoints:

### Root
- **`GET /`** (`app/main.py`): Health check endpoint returning service name, status, and docs URL.

### Diagnosis (`app/routers/diagnose.py`)
- **`POST /diagnose`**: Diagnoses a failed UPI Autopay/e-NACH mandate transaction. Parses the decline code to a category and explanation, logging the step in the audit trail.

### Prediction (`app/routers/predict.py`)
- **`GET /predict-retry-window/{customer_id}`**: Estimates the optimal retry window (liquidity predictor) for a specific customer based on their debit history.

### Scheduling & Execution (`app/routers/schedule.py`)
- **`POST /schedule-retry`**: Decides whether a transaction should be retried based on NPCI compliance limits (max 3 retries), bank uptime status, and customer self-scheduled dates. Consumes an NPCI retry attempt slot if scheduled, and fires a WhatsApp nudge to the customer.
- **`POST /execute-retry`**: Executes the most recent scheduled retry for a transaction. Calls the Razorpay client to attempt the debit (currently simulated) and updates transaction status based on success/failure.

### Customer Interaction (`app/routers/customer.py`)
- **`POST /customer-choose-date`**: Allows a customer to pick their own retry date via a link from the nudge message, pausing automated retries until the selected date.

### Audit Trail (`app/routers/audit_router.py`)
- **`GET /audit/{transaction_id}`**: Retrieves a cryptographic-like sequential audit trail of all actions (diagnosis, scheduling, nudges, execution) taken on a specific failed transaction.

### Dashboard (`app/routers/dashboard.py`)
- **`GET /dashboard/summary`**: Returns aggregated metrics (recovery rate, at-risk amount, API calls saved) for the frontend dashboard.
- **`GET /dashboard/live-feed`**: Returns a timeline feed of recent retry decisions and their outcomes.

### Transactions (`app/routers/transactions.py`)
- **`GET /transactions`**: Lists failed transactions, optionally filtered by status or decline category.
- **`GET /transactions/{transaction_id}`**: Retrieves comprehensive details for a specific transaction, including mandate details, decisions, and nudges.

---

## 2. Functionalities to be Performed (Production Readiness)

The current codebase is built for a demo/buildathon environment. The following functionalities must be completed before a production release:

1. **Automated Scheduler Integration (`scheduler.py`)**:
   - *Current State*: The `execute-retry` endpoint is invoked manually for the demo.
   - *To Perform*: Integrate a task scheduler (like APScheduler or Celery) to automatically trigger the retry logic when a decision's `chosen_slot_time` arrives in the real world.
2. **Database Migration (`database.py`)**:
   - *Current State*: Uses a local SQLite database (`sqlite:///./app.db`) for ease of setup.
   - *To Perform*: Update the `DATABASE_URL` environment variable to connect to a production-grade relational database like PostgreSQL or MySQL. Add Alembic for schema migrations.
3. **Real Razorpay Mandate Capture (`razorpay_client.py`)**:
   - *Current State*: Creates a standard test-mode Razorpay Order and uses random probabilities to simulate capture success.
   - *To Perform*: Integrate the actual Razorpay Subscriptions/Recurring Payments API (`/payments/create/recurring`), pulling the customer's saved token or e-mandate ID from the merchant's account to execute a real recurring debit.
4. **Machine Learning Model Integration (`liquidity_predictor.py`)**:
   - *Current State*: Uses a basic day-of-month frequency histogram and cohort fallbacks (heuristics) to predict liquidity.
   - *To Perform*: Replace `_customer_histogram` with a trained ML model (e.g., gradient boosting classifier or deep learning) that uses salary cycle features, bank balances (if available via Account Aggregator), and past behavioral data to output a true probabilistic score.
5. **Real-time Bank Outage Webhooks**:
   - *Current State*: Bank status is managed via a manually seeded `BankStatus` table.
   - *To Perform*: Listen to real-time webhooks from Razorpay or NPCI to update bank status asynchronously.

---

## 3. Inconsistencies & Placeholders to be Filled

The codebase relies on several mock implementations and simulations to function as a standalone demo. These need to be addressed:

- **Mocked Razorpay Debits (`app/razorpay_client.py`)**:
  - The `_simulated_attempt` function fakes a `pay_SIM...` Razorpay payment ID and uses `random.random()` to determine capture success.
  - Even if `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are provided, the code states: *"NOTE: actually capturing a recurring payment against a mandate requires the customer's saved token... For the buildathon demo we create the test-mode Order... and layer the same probabilistic capture outcome used in simulation on top of it."*
- **Mocked WhatsApp Nudges (`app/nudge.py`)**:
  - Sending WhatsApp messages via Twilio relies on `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`. If missing, the app simulates the message send and sets `simulated: True` in the database (`models.NudgeLog`).
- **Mocked Bank Uptime (`app/models.py`, `app/seed.py`)**:
  - The `BankStatus` table is referred to as a "Mock uptime table". During seeding, 6 banks are generated, with one explicitly hardcoded to `DOWN` to demonstrate the outage evasion path in the scheduler.
- **Cold-Start Data Generation (`app/main.py`, `app/seed.py`)**:
  - The backend runs `auto_seed_if_empty()` on startup to inject synthetic data (customers, mandates, debit history, failed transactions) if the database is empty. This is convenient for demos but should be removed or moved to a separate CLI command in production.
- **Hardcoded Return Types/Values**:
  - The liquidity predictor returns a default of `(after + timedelta(days=3), 0.25)` if there is absolutely no history. A more sophisticated default strategy might be required in production based on the merchant's industry.
