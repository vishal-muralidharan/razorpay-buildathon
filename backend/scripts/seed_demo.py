"""
Seeds a synthetic but realistic dataset:
  - 6 banks with a mock uptime status (one DOWN, to demo the outage path)
  - 25 customers, each with an Autopay/e-NACH mandate to a merchant
  - Debit history for most customers (a consistent "high-liquidity" day of
    month, with noise) so the liquidity predictor has real signal to learn
    from; a few customers are left with thin/no history to exercise the
    cohort-fallback path
  - 55 failed transactions spread across all 4 decline categories with
    varied timestamps, decline codes, and retry counts

Run standalone with `python -m app.seed` (uses its own DB session), or
imported and called with an existing session (as main.py does on startup).
"""
import os
import random
from datetime import datetime, timedelta, timezone

from app import models
from app.decline_parser import parse_decline_code
from app import audit

random.seed(42)

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Krishna", "Ishaan",
    "Ananya", "Diya", "Priya", "Kavya", "Sneha", "Neha", "Riya", "Meera",
    "Rohan", "Karthik", "Rahul", "Suresh", "Lakshmi", "Divya", "Pooja", "Anjali",
    "Manoj", "Vikram",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Nair", "Reddy", "Rao", "Gupta", "Menon",
    "Krishnan", "Pillai", "Bose", "Chowdhury", "Kapoor", "Joshi", "Naidu",
]

BANKS = ["HDFC", "ICICI", "SBI", "Axis", "Kotak", "IndusInd"]

DECLINE_CODES_WEIGHTED = (
    ["U19"] * 9 + ["U16"] * 4        # insufficient funds - most common by far
    + ["U30"] * 5 + ["U31"] * 2      # bank outage
    + ["U69"] * 4 + ["U67"] * 2      # mandate expired
    + ["U71"] * 3 + ["U72"] * 2 + ["U90"] * 1  # mandate cancelled
)

MERCHANTS = ["Vela SaaS", "SecureLife Insurance", "GrowMax SIP", "QuickLoan EMI"]


def _random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _random_phone():
    return "+91" + str(random.randint(7000000000, 9999999999))


def run_seed(db):
    assert os.getenv("ENABLE_AUTO_SEED") == "true", "ENABLE_AUTO_SEED must be explicitly set to 'true' to run the seed script."
    now = datetime.now(timezone.utc)

    # --- Bank status (mock uptime tracker) -----------------------------
    for i, bank in enumerate(BANKS):
        status = "DOWN" if bank == "IndusInd" else "UP"  # one bank mid-outage for the demo
        db.add(models.BankStatus(bank_name=bank, status=status, updated_at=now))
    db.commit()

    customers = []
    mandates = []

    # --- Customers + mandates -------------------------------------------
    for i in range(25):
        cust = models.Customer(
            name=_random_name(),
            phone=_random_phone(),
            preferred_language=random.choice(["hi-en", "ta-en", "te-en", "en"]),
        )
        db.add(cust)
        db.flush()
        customers.append(cust)

        mandate = models.Mandate(
            customer_id=cust.id,
            amount=round(random.choice([199, 299, 499, 999, 1499, 2499, 4999]), 2),
            frequency="MONTHLY",
            created_at=now - timedelta(days=random.randint(60, 500)),
            status="ACTIVE",
            subscription_age_days=random.randint(30, 480),
            merchant_name=random.choice(MERCHANTS),
            bank_name=random.choice(BANKS),
            razorpay_customer_id=f"cust_{i}_{random.randint(1000,9999)}",
            razorpay_token_id=f"token_{i}_{random.randint(1000,9999)}"
        )
        db.add(mandate)
        db.flush()
        mandates.append(mandate)
    db.commit()

    # --- Debit history (feeds the liquidity predictor) -------------------
    # First 20 customers get a clear personal pattern (their "salary day"
    # +/- a day or two of noise) over the last 6 months so the personal
    # histogram path has real signal. Last 5 are left thin (0-2 records)
    # so the demo can show the cohort-fallback path kicking in.
    for idx, cust in enumerate(customers):
        if idx < 20:
            salary_day = random.choice([1, 5, 7, 10, 15, 28])
            for m in range(6):
                noisy_day = max(1, min(salary_day + random.choice([-1, 0, 0, 0, 1]), 28))
                debit_date = (now - timedelta(days=30 * m)).replace(day=noisy_day)
                db.add(models.DebitHistory(
                    customer_id=cust.id,
                    debit_date=debit_date,
                    day_of_month=debit_date.day,
                    amount=mandates[idx].amount,
                ))
        else:
            for m in range(random.choice([0, 1, 2])):
                debit_date = now - timedelta(days=30 * (m + 1))
                db.add(models.DebitHistory(
                    customer_id=cust.id,
                    debit_date=debit_date,
                    day_of_month=debit_date.day,
                    amount=mandates[idx].amount,
                ))
    db.commit()

    # --- Failed transactions (55, spread over the last 30 days) ----------
    txn_count = 55
    for i in range(txn_count):
        cust_idx = random.randrange(len(customers))
        cust = customers[cust_idx]
        mandate = mandates[cust_idx]
        code = random.choice(DECLINE_CODES_WEIGHTED)
        category, explanation = parse_decline_code(code)
        failed_at = now - timedelta(
            days=random.randint(0, 29), hours=random.randint(0, 23), minutes=random.randint(0, 59)
        )

        txn = models.FailedTransaction(
            mandate_id=mandate.id,
            customer_id=cust.id,
            amount=mandate.amount,
            decline_code=code,
            decline_category=category,
            failed_at=failed_at,
            retry_count=0,
            status=models.TransactionStatus.PENDING.value,
        )
        db.add(txn)
        db.flush()

        # Pre-seed the diagnosis audit step so the dashboard has content
        # immediately after seeding; POST /diagnose remains fully callable
        # (and idempotent) for the live demo walkthrough.
        audit.log_step(db, txn.id, "DIAGNOSIS", {
            "decline_code": code, "category": category, "explanation": explanation,
            "seeded": True,
        })
    db.commit()

    print(f"Seeded {len(customers)} customers, {len(mandates)} mandates, {txn_count} failed transactions.")


if __name__ == "__main__":
    from app.database import SessionLocal, Base, engine
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        run_seed(session)
    finally:
        session.close()
