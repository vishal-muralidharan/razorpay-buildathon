# Razorpay Buildathon

AI revenue recovery agent for failed UPI Autopay payments, optimizing smart retry schedules within NPCI budget limits.

## Overview

Recurring payment failures across UPI Autopay and e-NACH often burn through NPCI's strict 3-retry limit by retrying blindly every 24 hours. The Mandate Resurrection Agent analyzes debit failure reasons, predicts when the customer will have liquidity based on historical debit patterns, schedules retries outside banking peak hours, and nudges customers before executing retries via Razorpay.

## Architecture

The system consists of 5 decoupled components connected through an audit ledger:

```text
[ Webhook Ingestion ]
         │
         ▼
[ Diagnosis Engine ] ──► Classifies decline code (insufficient funds, bank outage, expired)
         │
         ▼
[ Liquidity Predictor ] ──► Computes optimal retry date via debit history histogram
         │
         ▼
[ Compliance Scheduler ] ──► Enforces 3-retry limit, blackout hours (18:00 to 21:00), bank health
         │
         ▼
[ Nudge & Execution ] ──► Sends WhatsApp and SMS alerts, executes charge via Razorpay
         │
         ▼
[ Audit Ledger ] ──► SHA-256 hash-chained log for every state transition
```

1. **Diagnosis Engine (`app/routers/diagnose.py`):** categorizes raw NPCI response codes into failure classes.
2. **Liquidity Predictor (`app/liquidity_predictor.py`):** evaluates past successful debits to score the best retry day.
3. **Compliance Scheduler (`app/scheduler.py`):** enforces NPCI limits, avoids high-traffic banking hours, and pauses on customer choices.
4. **Nudge and Execution (`app/nudge.py`, `app/razorpay_client.py`):** dispatches Twilio notifications and charges mandate tokens.
5. **Audit Ledger (`app/audit.py`):** records cryptographic hash chains verifying every decision and payment event.

## Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| Backend | Python, FastAPI | High throughput async I/O, fast data validation, and native OpenAPI documentation. |
| Database | SQLite, SQLAlchemy, Alembic | Lightweight local setup with zero external daemons and versioned migrations. |
| Machine Learning | NumPy, SciPy | Explainable day-of-month frequency histogram models without black-box overfitting. |
| Frontend | React 18, Vite, Tailwind CSS | Fast responsive single-page application dashboard with real-time status polling. |
| Charts | Recharts | Declarative SVG financial trend charts and recovery telemetry. |
| Testing | Pytest, Vitest | Backend API integration testing and frontend component unit validation. |

## Setup and Installation

### Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher and npm
- SQLite 3

### Backend Setup

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
ENABLE_AUTO_SEED=true python -m scripts.seed_demo
```

### Frontend Setup

```bash
cd frontend
npm ci
```

### Environment Variables

Environment variables are configured in `.env` files in each subfolder. The system falls back to simulation mode if third-party credentials are omitted.

In `backend/.env`:

- `DATABASE_URL`
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `TEMPLATE_SID_INSUFFICIENT_FUNDS`
- `TEMPLATE_SID_BANK_OUTAGE`
- `TEMPLATE_SID_MANDATE_EXPIRED`
- `TEMPLATE_SID_MANDATE_CANCELLED`
- `ALLOWED_ORIGINS`
- `JWT_SECRET`
- `OIDC_ISSUER`
- `OIDC_AUDIENCE`
- `ENABLE_AUTO_SEED`

In `frontend/.env`:

- `VITE_API_BASE_URL`
- `VITE_RAZORPAY_KEY_ID`

Never commit secrets or `.env` files to git.

## Quick Start: How to Run and Test

### Running the Services

Start the backend API server:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Start the frontend dashboard:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser. API documentation is available at `http://localhost:8000/docs`.

### Running Tests

Run backend tests:

```bash
cd backend
python -m pytest
```

Run frontend tests:

```bash
cd frontend
npm run test
```

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/diagnose` | POST | Classifies a raw NPCI decline code into a recovery category |
| `/predict-retry-window/{customer_id}` | GET | Returns the predicted optimal retry date and confidence score |
| `/schedule-retry` | POST | Applies compliance rules and schedules the next debit attempt |
| `/customer-choose-date` | POST | Saves a customer self-scheduled date and pauses automated retries |
| `/execute-retry` | POST | Executes the scheduled retry charge via Razorpay or the simulator |
| `/audit/{transaction_id}` | GET | Returns the full SHA-256 hash-chained audit trail and integrity check |
| `/dashboard/summary` | GET | Returns aggregated recovery statistics and ROI metrics |
| `/dashboard/live-feed` | GET | Returns recent retry decisions in reverse chronological order |
| `/transactions` | GET | Lists failed transactions with status and customer filters |
| `/transactions/{id}` | GET | Returns detailed drill-down data for a single transaction |

## Data Model

The database schema (`backend/app/models.py`) includes 7 core models:

- `Customer`: customer identity, contact information, and linked payment profile.
- `Mandate`: UPI Autopay and e-NACH mandate metadata, bank identifier, and recurring token ID.
- `FailedTransaction`: debit failure records, decline reason codes, and resolution states.
- `DebitHistory`: past successful debits used for liquidity histogram prediction.
- `RetryDecision`: compliance-evaluated retry attempts, target dates, and confidence scores.
- `AuditLog`: tamper-evident SHA-256 hash chain linking previous hash, payload, and timestamp.
- `BankStatus`: simulated bank outage states and downtime deferral windows.

## Key Decisions and Tradeoffs

1. **Histogram frequency modeling over deep learning:** a monthly subscription generates at most 12 debits per year per customer. This sample size is too small for supervised deep learning without overfitting. Day-of-month frequency histograms provide transparent and defensible recommendations.
2. **Strict compliance enforcement:** NPCI caps retries at 3 attempts per cycle. The scheduler rejects any 4th attempt with HTTP 400 and marks the transaction as exhausted. Debits are automatically deferred out of high-traffic hours (18:00 to 21:00).
3. **Customer self-scheduling override:** customer selected dates take precedence over automated algorithm recommendations.
4. **Cryptographic audit logging:** every state change writes a SHA-256 hash covering `prev_hash + step + payload + timestamp` to ensure non-repudiation.

## Known Limits

- **Synthetic tokens in simulation:** real UPI Autopay mandates require browser-based authorization through Razorpay Checkout.js. The simulator uses synthetic tokens for testing retry execution.
- **WhatsApp templates:** real Twilio production deployment requires Meta template approval for Content SIDs.
- **Authentication:** local development uses demo merchant bearer tokens. Production requires an identity provider issuing signed JWTs.
- **Liquidity signals:** the system infers liquidity from historical debits rather than real-time Account Aggregator bank balance feeds.

## Deployment

The application runs in 2 tiers:

- **Frontend:** compiled into static assets with `npm run build` in `frontend` and hosted on Vercel.
- **Backend:** hosted as an ASGI web application with Uvicorn.
- **Configuration:** database URLs and API keys are managed through server environment variables.

## Author and License

Created by Vishal Muralidharan.
Distributed under the MIT License.
