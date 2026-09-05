from app.database import SessionLocal
from app import models
import traceback
db = SessionLocal()
try:
    txns = db.query(models.FailedTransaction).join(models.Mandate).filter(models.Mandate.merchant_name == "Vela SaaS").all()
    print("Success:", len(txns))
except Exception as e:
    traceback.print_exc()
