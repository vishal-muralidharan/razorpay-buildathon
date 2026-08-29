# Mandate Resurrection Agent: Complete Feature Guide

This document outlines the complete feature set of the Mandate Resurrection Agent, why each feature is critical for the product, and how to thoroughly test them in a local environment.

---

## 1. NPCI Decline Parsing & Diagnosis
**Where it lives**: `backend/app/decline_parser.py`, `backend/app/routers/diagnose.py`

### What it is
A parser that maps raw NPCI failure codes (e.g., `INSUFFICIENT_FUNDS`, `BANK_OUTAGE`, `MANDATE_EXPIRED`) into structured, actionable categories.

### Why it's needed
Blindly retrying all failures is inefficient and burns through the hard NPCI 3-retry-per-cycle limit. By differentiating root causes, the system can skip unrecoverable errors (like a cancelled mandate) and intelligently defer retries during bank outages.

### How to test
1. Open the frontend dashboard and select a failed transaction.
2. Click the **Diagnose** button.
3. Observe the transaction state change from `FAILED` to a categorized state (e.g., `INSUFFICIENT_FUNDS_DIAGNOSED`).
4. **API Test**: Send a `POST` request to `/diagnose` with a raw failure code and verify the correct category is returned.

---

## 2. ML-Based Liquidity Prediction
**Where it lives**: `backend/app/liquidity_predictor.py`, `backend/app/routers/predict.py`

### What it is
An XGBoost model (with SHAP explainability) that analyzes a customer's historical successful debits to predict the day of the month they are most likely to have liquidity (e.g., a salary day). It uses a cohort-level fallback if the customer lacks sufficient history.

### Why it's needed
It maximizes the probability of successful recovery by retrying the debit exactly when the user has funds, rather than making random, uninformed guesses that could waste retry attempts.

### How to test
1. From the transaction drill-down drawer, click **Schedule retry**.
2. Notice that it routes to a specific date rather than an immediate retry.
3. **API Test**: Send a `GET` request to `/predict-retry-window/{customer_id}`. Ensure it returns a specific day of the month and a confidence score based on their history.

---

## 3. Compliant Scheduling Engine
**Where it lives**: `backend/app/scheduler.py`, `backend/app/routers/schedule.py`, `backend/app/jobs.py`

### What it is
An automated retry scheduler (backed by `APScheduler`) that strictly enforces NPCI compliance rules:
- Maximum 3 retries per cycle.
- Defers retries outside of high-traffic banking hours (18:00 - 21:00).
- Pauses attempts if the destination bank is experiencing an outage.

### Why it's needed
To remain compliant with NPCI regulations. Violating these rules can lead to penalizations, mandate blocking, and merchant bans.

### How to test
1. In the frontend, repeatedly click **Schedule** -> **Execute via Razorpay** on a single transaction.
2. Observe the attempt count increasing.
3. On the 4th attempt, the system will block the request (HTTP 400) and mark the transaction as `EXHAUSTED`.
4. Try scheduling a retry between 18:00 and 21:00; the system will log a push of the retry to 21:00.

---

## 4. Omnichannel Customer Nudges & Self-Scheduling
**Where it lives**: `backend/app/nudge.py`, `backend/app/routers/customer.py`

### What it is
An integration with Twilio to send WhatsApp templates when a payment fails. It provides the customer with context and a way to manually select a retry date. When a date is chosen, automated retries are paused until that day.

### Why it's needed
Direct, polite engagement reduces involuntary churn. Allowing the customer to self-schedule puts them in control and practically guarantees the funds will be available when the retry happens.

### How to test
1. Ensure the Twilio credentials are provided (or allow it to fall back to the simulated logger).
2. Schedule a retry in the UI; observe the "WhatsApp message sent" in the audit timeline.
3. **API Test**: Hit `POST /customer-choose-date` with the transaction ID.
4. Verify the transaction status changes to `AWAITING_CUSTOMER`, preventing further automated retries until the chosen date.

---

## 5. Tamper-Evident Audit Ledger
**Where it lives**: `backend/app/audit.py`, `backend/app/routers/audit_router.py`

### What it is
A cryptographic hash chain that logs every state change, prediction, schedule decision, and nudge for a transaction. It uses sequentially linked SHA-256 hashes (`hash = sha256(prev_hash + data)`).

### Why it's needed
Crucial for regulatory compliance and dispute resolution. If a customer or auditor questions why a debit was attempted on a specific date, this ledger provides mathematical proof of the ML prediction and scheduling rules, demonstrating that the system acted correctly and the logs haven't been retroactively modified.

### How to test
1. Perform multiple actions on a transaction (diagnose, schedule, execute).
2. Open the **Audit Drawer** in the frontend for that transaction.
3. Verify the visual timeline confirms `chain_valid: true`.
4. **API Test**: Send a `GET` request to `/audit/{transaction_id}` and manually verify that each log's `prev_hash` strictly matches the preceding log's `hash`.

---

## 6. Bank Outage Webhooks & Resilience
**Where it lives**: `backend/app/routers/webhook.py`

### What it is
An endpoint and background process that tracks downstream NPCI and bank downtime dynamically.

### Why it's needed
Prevents the system from executing debits against a banking network that is known to be failing, which would waste precious retry attempts and fail anyway.

### How to test
1. Send a `POST` request to `/webhook/bank-status` with a payload indicating a specific bank is `DOWN`.
2. Attempt to schedule a retry for a customer using that bank.
3. Observe that the retry is instantly deferred rather than executed.

---

## 7. Razorpay Execution Sandbox
**Where it lives**: `backend/app/razorpay_client.py`

### What it is
An execution engine for the retries. It dynamically uses real Razorpay test-mode API credentials if provided, or seamlessly falls back to a simulated execution sandbox.

### Why it's needed
This is the final step of the pipeline that actually executes the mandate and recovers the merchant's revenue.

### How to test
1. **Simulation Mode**: Run the app without Razorpay credentials in `.env`. Click **Execute via Razorpay** on the frontend and observe the simulated success.
2. **Live Test Mode**: Export `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`. Click **Execute via Razorpay** and verify that a real API call is placed to the Razorpay test environment.

---

## 8. Merchant ROI & Analytics Dashboard
**Where it lives**: `frontend/src/components/`, `backend/app/routers/dashboard.py`

### What it is
A React-based UI that presents a real-time view of:
- **KPI Strip**: Total ₹ recovered, ₹ at risk, and the overall recovery rate.
- **Root Cause Analysis**: A breakdown of why transactions are failing (e.g., % Insufficient Funds vs. % Bank Outages).
- **Live Feed**: A chronological feed of all retry decisions and nudges happening across the system.

### Why it's needed
Provides merchants with deep visibility into the value the AI agent is delivering. It shifts the narrative from "failed payments" to "recovered revenue".

### How to test
1. Ensure the frontend is running (`npm run dev`).
2. Navigate to `http://localhost:5173`.
3. Process a few transactions by scheduling and executing retries.
4. Verify that the KPI strip instantly updates the "Recovered" amount and adjusts the recovery percentage.

---

## 9. Interactive Transaction Drill-Down
**Where it lives**: `frontend/src/components/AuditDrawer.jsx`, `frontend/src/components/TransactionTable.jsx`

### What it is
A detailed inspection view for individual failed transactions. It exposes the ML prediction confidence, the timeline of nudges, and the cryptographic audit trail all in one unified drawer.

### Why it's needed
Gives merchants and support staff granular insight into *why* the AI made specific decisions, empowering them to manually override if necessary or confidently explain the system's actions to a customer.

### How to test
1. On the main dashboard, click on any transaction row in the table.
2. The drawer will slide out from the right.
3. Inspect the ML confidence score, the sequence of events, and ensure all buttons (Diagnose, Schedule, Execute) work exactly as expected for that specific transaction context.
