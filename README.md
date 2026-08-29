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
uvicorn app.main:app --reload --port 8000
```

The app auto-seeds 25 customers, 25 mandates, and 55 synthetic failed
transactions on first boot (SQLite file `mandate_resurrection.db`, created
next to `app/`). Delete that file and restart to re-seed from scratch.
API docs: `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. It talks to the backend at
`http://localhost:8000` by default — override with `VITE_API_BASE_URL` in
`frontend/.env` if you run the API elsewhere.

### Optional: real Razorpay / Twilio credentials

Both integrations run in a clearly-labeled **simulation mode** out of the
box, so the whole system works offline with no keys. To use real
test-mode APIs, set these env vars before starting the backend:

```bash
export RAZORPAY_KEY_ID=rzp_test_xxx
export RAZORPAY_KEY_SECRET=xxx
export TWILIO_ACCOUNT_SID=xxx
export TWILIO_AUTH_TOKEN=xxx
export TWILIO_FROM_NUMBER=+1415xxxxxxx
```

No code changes needed — `app/razorpay_client.py` and `app/nudge.py` check
for these and fall back to simulation automatically if they're absent.

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

## Demo script

1. Open the dashboard — 55 seeded failures, broken down by root cause.
2. Click an `INSUFFICIENT_FUNDS` transaction → **Diagnose** → **Schedule
   retry**: watch it get routed to a predicted high-balance date instead
   of an immediate retry, and a WhatsApp nudge appear below.
3. Click **Execute via Razorpay** to simulate the debit attempt landing
   on that date.
4. Repeat schedule → execute two more times, then click **Try 4th retry**
   — the API returns 400 and the transaction is marked cap-exhausted.
5. Scroll the audit ledger for that transaction: every step is
   hash-chained, `chain_valid: true`.
6. Back on the dashboard, watch ₹ recovered / at risk and the recovery
   rate update.

## What's stubbed for the hackathon cut (see build brief §3)

- Bank outage detection uses a manually-seeded `BankStatus` table, not a
  live monitoring feed.
- The mandate-health score is implicit in the category routing rather
  than a separate scored table — this can be added as its own module
  without changing the scheduler's interface.
- The self-scheduling "portal" is the 3-date list embedded in the nudge
  message plus `POST /customer-choose-date`, rather than a hosted page.
- The re-mandate generator and the fallback UPI QR rail are not built —
  `MANDATE_EXPIRED`/`MANDATE_CANCELLED` transactions are correctly routed
  away from retries and marked `CANCELLED`, ready for either to plug in.
