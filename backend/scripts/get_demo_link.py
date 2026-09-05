import sys
import os

# Ensure the app module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app import models
from app.auth import generate_customer_token

def get_demo_link():
    db = SessionLocal()
    
    # Get the most recent transaction
    txn = db.query(models.FailedTransaction).order_by(models.FailedTransaction.id.desc()).first()
    if not txn:
        print("No transactions found. Run the webhook simulator first.")
        db.close()
        return

    # Generate a secure JWT for this transaction
    token = generate_customer_token(txn.id)
    
    link = f"http://localhost:5173/schedule?token={token}"
    
    print(f"🔗 Customer Self-Serve Link for Transaction #{txn.id} ({txn.customer.name})")
    print(f"\n{link}\n")
    print("Click or copy this link into your browser to show the Customer UI.")

    db.close()

if __name__ == "__main__":
    get_demo_link()
