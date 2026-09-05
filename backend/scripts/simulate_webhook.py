import sys
import os

# Ensure the app module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from datetime import datetime, timezone
from app.database import SessionLocal
from app import models

def inject_synthetic_failure():
    db = SessionLocal()
    
    # Pick a random customer and their mandate
    mandate = db.query(models.Mandate).order_by(models.Mandate.id.desc()).first()
    if not mandate:
        print("No mandates found. Please run seed_demo.py first.")
        db.close()
        return
    
    # Randomly select a decline scenario
    scenarios = [
        ("INSUFFICIENT_FUNDS", "U69", [199, 499, 999]),
        ("BANK_OUTAGE", "U72", [299, 599, 1299]),
        ("MANDATE_EXPIRED", "U18", [49, 99])
    ]
    
    category, code, amounts = random.choice(scenarios)
    amount = random.choice(amounts)
    
    txn = models.FailedTransaction(
        customer_id=mandate.customer_id,
        mandate_id=mandate.id,
        amount=amount,
        decline_code=code,
        decline_category=category,
        failed_at=datetime.now(timezone.utc),
        status=models.TransactionStatus.PENDING.value,
        retry_count=0
    )
    
    db.add(txn)
    db.commit()
    db.refresh(txn)
    
    print(f"✅ Success! Simulated incoming webhook:")
    print(f"   Transaction ID : {txn.id}")
    print(f"   Customer       : {mandate.customer.name}")
    print(f"   Amount         : ₹{txn.amount}")
    print(f"   Reason         : {txn.decline_category}")
    print("\nCheck your dashboard - it should auto-refresh and display this new failure within 8 seconds.")
    
    db.close()

if __name__ == "__main__":
    inject_synthetic_failure()
