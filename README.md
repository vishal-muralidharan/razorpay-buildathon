# Mandate Resurrection Agent

**Track 03 — AI Revenue Recovery**

An agent that diagnoses why a UPI Autopay / e-NACH recurring payment failed,
predicts the day a retry is most likely to succeed, and spends NPCI's
hard 3-retry-per-cycle budget on purpose instead of burning it on blind
24-hour retries.

```
Failed debit → diagnose → predict best window → schedule within compliance
     rules → nudge the customer → execute via Razorpay → log every step
     to a tamper-evident audit ledger → surface it all on a ROI dashboard
```

## Quick start

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt --break-system-packages   # drop the flag in a venv
alembic upgrade head                                       # create the database schema
ENABLE_AUTO_SEED=true python -m scripts.seed_demo           # 25 customers, 55 failed transactions
uvicorn app.main:app --reload --port 8000
```

The database is a local SQLite file (`mandate_resurrection.db`, created
next to `app/`). It does **not** auto-seed on startup - run the seed
command above once after creating the schema. To start over, delete the
file, re-run `alembic upgrade head`, then re-seed.
API docs: `http://localhost:8000/docs`.

Every endpoint except the webhooks requires a merchant bearer token. For
local testing, use the demo token:

```
Authorization: Bearer secret-vela
```

(`app/auth.py` maps a handful of hardcoded demo tokens to merchant names -
see that file for the full list. A real deployment replaces this with a
proper identity provider - see "Adding real Razorpay UPI" below.)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. It talks to the backend at
`http://localhost:8000` by default — override with `VITE_API_BASE_URL` in
`frontend/.env` if you run the API elsewhere.

### Configuration (.env)

The project includes a `backend/.env.example` file that outlines the optional API keys (Razorpay, Twilio, Auth0). You do **not** need to provide these for local testing or hackathon submissions — the system automatically falls back to simulation mode (synthetic data and mock tokens) if they are missing. 

If you plan to use real test-mode APIs, copy the example file:
```bash
cp backend/.env.example backend/.env
```
And populate it with your `RAZORPAY_KEY_ID`, `TWILIO_ACCOUNT_SID`, etc. No code changes are needed — `app/razorpay_client.py` and `app/nudge.py` check for these and fall back to simulation automatically.

---

## The liquidity-window model — what it is and why

**Approach: a day-of-month frequency histogram, not a trained classifier.**

For each customer, the model looks at their `DebitHistory` (past
*successful* debits), counts which day of the month those debits landed
on, and recommends the next occurrence of the most common day. The
confidence score is simply `(count of that day) / (total debits on file)`.

If a customer has fewer than 3 historical debits (a new subscriber, or one
who's mostly paid on time), there isn't enough personal signal to trust —
the model falls back to a **cohort-level histogram** built across every
customer's debit history, with the confidence score capped at 0.5 to
reflect that it's a population-level guess, not a personal one.

**Why this fits the problem better than a trained model would, here:**

1. **Data volume.** A monthly subscription produces at most ~12 successful
   debits a year per customer. That's far too little to fit a supervised
   model per customer without serious overfitting.
2. **Explainability matters more than a few points of accuracy.** The
   output feeds a decision that's constrained by a hard compliance cap —
   "we picked the 7th because you were paid successfully on the 6th, 7th,
   and 8th three months running" is auditable and defensible. A gradient-
   boosted black box making the same call, on the same data volume, isn't
   more accurate and is much harder to justify to a compliance reviewer.
3. **Day-of-month is a strong, cheap signal.** Salaries, EMI clearances,
   and most recurring inflows in India are strongly periodic by calendar
   day, so this captures most of the realistically available signal for
   very little modeling cost.

The function signature (`predict_liquidity_window(db, customer_id)` in
`app/liquidity_predictor.py`) is deliberately the seam for a future
upgrade — a trained model could replace the histogram behind the same
interface without touching any caller.

---

## Compliance rules implemented, mapped to NPCI's requirements

| NPCI requirement | Where it's enforced | How |
|---|---|---|
| Max 3 debit attempts per mandate per billing cycle | `POST /schedule-retry` in `app/routers/schedule.py`, gated by `app/scheduler.py::MAX_RETRIES` | A 4th scheduling request returns **HTTP 400** and the transaction is marked `EXHAUSTED`. Verified live: see demo script below. |
| No retries during high-traffic banking hours | `app/scheduler.py::_push_out_of_peak_hours` | Any candidate slot between 18:00–21:00 is pushed to 21:00 the same day — the predicted *date* is kept, only the *hour* moves. |
| Don't retry a dead mandate | `app/scheduler.py::decide_retry` | `MANDATE_EXPIRED` / `MANDATE_CANCELLED` never consume a retry slot at all — they're routed to the re-mandate flow instead, and the transaction is marked `CANCELLED` without touching `retry_count`. |
| Don't retry blindly into a known bank outage | `app/scheduler.py::decide_retry`, backed by the mock `BankStatus` table | `BANK_OUTAGE` failures check the bank's status flag; if still `DOWN`, the retry is deferred by a recheck interval instead of firing immediately. |
| Customer consent / self-scheduling should override automation | `POST /customer-choose-date` in `app/routers/customer.py`, checked at the top of `schedule-retry` | Once a customer picks a date, the transaction moves to `AWAITING_CUSTOMER` and further `schedule-retry` calls are no-ops until that date passes. |
| Every decision must be auditable | `app/audit.py` | Every diagnosis, scheduling decision, nudge, and execution writes a `AuditLog` row whose hash covers `prev_hash + step + payload + timestamp` — a SHA-256 hash chain per transaction. `GET /audit/{id}` recomputes and verifies the whole chain. |

---

## API reference

| Endpoint | Purpose |
|---|---|
| `POST /diagnose` | Maps a transaction's raw NPCI decline code to a category |
| `GET /predict-retry-window/{customer_id}` | Returns the predicted best retry date + confidence |
| `POST /schedule-retry` | Runs the compliance-gated scheduling decision, sends the customer nudge |
| `POST /customer-choose-date` | Customer self-schedule; pauses automated retries |
| `POST /execute-retry` | Executes the most recently scheduled attempt via Razorpay (or simulator) |
| `GET /audit/{transaction_id}` | Full hash-chained audit trail + tamper-check result |
| `GET /dashboard/summary` | ROI numbers for the merchant dashboard |
| `GET /dashboard/live-feed` | Recent retry decisions, newest first |
| `GET /transactions` | List/filter failed transactions |
| `GET /transactions/{id}` | Full drill-down: mandate, decisions, nudges |

Full interactive docs at `/docs` once the backend is running.

---

## Live Demo (Dynamic Data)

Since the dashboard auto-refreshes every 8 seconds, you can easily demonstrate the system's real-time reactivity without needing external webhooks.

1. Start both the backend and frontend servers as described in the Quick Start.
2. Open the Merchant Dashboard at `http://localhost:5173`.
3. In a new terminal, activate the backend environment and run the webhook simulation script:
   ```bash
   cd backend
   source venv/bin/activate
   python -m scripts.simulate_webhook
   ```
4. This script injects a randomized failed transaction directly into the database.
5. **Watch the dashboard** — within 8 seconds (no page refresh required!), the new transaction will magically appear in the "Failed Transactions" table with a `Pending diagnosis` status.
6. Click the transaction, hit **Diagnose & Schedule**, and watch the ML engine process it and push it into the "Live decision feed".
7. Click **Execute via Razorpay** to simulate the debit attempt landing on that date.
8. Scroll the audit ledger for that transaction to see the SHA-256 hash-chained logs.

## Adding real Razorpay UPI

The current code only ever executes the *retry* step for a mandate that
already exists - it has no flow for actually creating one. Real UPI
Autopay has three distinct phases, and only the third is built:

1. **Mandate registration** (not built) - the customer authorises a UPI
   Autopay mandate through Razorpay Checkout. This needs its own endpoint
   and a small customer-facing page:
   - `POST /customers` to get a `customer_id` for the payer.
   - `POST /orders` for ₹1 (UPI mandate authorisation orders are ₹1,
     not the real recurring amount) with the recurring/token parameters
     Razorpay's Standard Checkout expects for UPI Autopay.
   - Load Razorpay's Checkout.js with that order and let the customer
     approve the mandate in their UPI app (Google Pay/PhonePe/etc.) -
     this step cannot be done server-side, it needs a browser.
   - On success, Razorpay returns a `token` tied to that customer. Save
     it into `Mandate.razorpay_customer_id` / `razorpay_token_id` (the
     columns already exist - `seed_demo.py` currently fills them with
     fake values as a stand-in for this step).
2. **Tokenisation** - handled by Razorpay once step 1 succeeds; nothing
   to build here beyond storing the token as above.
3. **Charging retries** (built, `app/razorpay_client.py`) - creates a new
   order and a recurring payment referencing the stored token. This is
   the part `execute_retry_job` already calls.

**Before wiring in real keys**, confirm the exact request shape against
Razorpay's own API reference rather than trusting this codebase's
guesses - endpoint paths and required fields for recurring charges do
shift, and getting them wrong with live test-mode keys is a more
confusing failure mode than a 404. Start at
`https://razorpay.com/docs/payments/recurring-payments/` and the
UPI-specific page under it.

**Webhook setup** (`app/routers/webhook.py` is already built for this):
1. In the Razorpay Dashboard (test mode), go to Settings → Webhooks and
   add an endpoint for `payment.captured` and `payment.failed`.
2. Since your local machine has no public URL, use `ngrok http 8000` and
   register the ngrok URL + `/webhook/razorpay` as the webhook.
3. Copy the webhook secret Razorpay generates into
   `RAZORPAY_WEBHOOK_SECRET` - this is what `verify_signature()` checks.

## Testing it

1. **Without real credentials** (default): `execute-retry` resolves
   immediately using the simulator - this is what the existing
   `tests/test_endpoints.py` suite exercises, and what the demo script
   above walks through by hand.
2. **With real test-mode credentials**, once mandate registration (above)
   is built and a mandate has a real token: set `RAZORPAY_KEY_ID` /
   `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET`, run `ngrok`, and:
   - Call `/schedule-retry` then `/execute-retry` as normal - the
     transaction should move to `PENDING_CONFIRMATION` (a real API call
     was placed, not a simulated one).
   - Razorpay's test mode lets you simulate a UPI approval/decline from
     its dashboard, which should fire your webhook and resolve the
     transaction to `RECOVERED` or back to `PENDING`/`EXHAUSTED` - verify
     this by watching `GET /transactions/{id}` before and after.
   - If you want to trigger the webhook manually instead of waiting on
     Razorpay's test simulator, `backend/mock_webhook.py` sends the same
     payload shape by hand - useful for testing the webhook handler in
     isolation before real credentials are ready.
3. Either way, run `pytest tests/ -v` after any change to the scheduler,
   the webhook handler, or the routers - `test_endpoints.py` hits the
   real HTTP layer and would have caught several of the bugs fixed in
   this audit; `test_scheduler.py` covers the compliance-rule matrix in
   isolation. Add a case to whichever file matches the layer you changed.

## What's still stubbed

Most of the original hackathon-cut list has since been built out (see
`AUDIT_v2.md` for the full before/after). What's left standing between
this and a real production deployment:

- **Razorpay tokens are synthetic.** `scripts/seed_demo.py` generates fake
  `razorpay_customer_id`/`razorpay_token_id` values. A real deployment
  needs an actual mandate-onboarding flow that captures these from
  Razorpay when the customer first authorizes their UPI Autopay mandate -
  see "Adding real Razorpay UPI" below.
- **WhatsApp template SIDs are placeholders** (`app/nudge.py`). Real
  Content SIDs require drafting the templates and getting them approved
  by Meta through the Twilio console first.
- **Auth is a hardcoded token map** (`app/auth.py`). Fine for a demo with
  one team's merchants; a real deployment needs a proper identity
  provider issuing per-merchant JWTs.
- **The ML model trains on synthetic data at startup** (`train_mock_model`
  in `app/liquidity_predictor.py`). Real balance signals require an
  Account Aggregator integration (Setu/Finvu) with customer consent - a
  compliance and UX project in its own right, not just a data swap.
- **Bank outage detection is inferred from your own decline-rate spikes**,
  not a live feed from NPCI or the bank - there isn't a public one to
  subscribe to. `POST /webhook/bank-status` exists so a downstream partner
  can push updates if they have one.
