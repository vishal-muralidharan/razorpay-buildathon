from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine, SessionLocal
from app import models  # noqa: F401 - ensures models are registered before create_all
from app.routers import diagnose, predict, schedule, customer, audit_router, dashboard, transactions, webhook, registration

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Mandate Resurrection Agent",
    description="Diagnoses failed UPI Autopay/e-NACH mandates, predicts the best retry "
                "window, and recovers revenue within NPCI's 3-retry compliance cap.",
    version="1.0.0",
)

import os
import json

ALLOWED_ORIGINS = json.loads(os.getenv("ALLOWED_ORIGINS", '["http://localhost:5173", "http://localhost:3000"]'))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagnose.router)
app.include_router(predict.router)
app.include_router(schedule.router)
app.include_router(customer.router)
app.include_router(audit_router.router)
app.include_router(dashboard.router)
app.include_router(transactions.router)
app.include_router(webhook.router)
app.include_router(registration.router)


@app.get("/")
def root():
    return {
        "service": "Mandate Resurrection Agent",
        "status": "up",
        "docs": "/docs",
    }


@app.on_event("startup")
def startup_event():
    """Convenience for the demo: seed synthetic data automatically on first
    boot if the database is empty, so `uvicorn app.main:app` alone is
    enough to get a working demo. Safe to remove for a real deployment."""
    from app.scheduler_setup import start_scheduler
    from app.liquidity_predictor import train_mock_model
    
    start_scheduler()
    train_mock_model()

    # Removed auto-seeding. Run scripts/seed_demo.py manually with ENABLE_AUTO_SEED=true
    pass

@app.on_event("shutdown")
def shutdown_event():
    from app.scheduler_setup import scheduler
    scheduler.shutdown()
