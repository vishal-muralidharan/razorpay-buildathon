from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from app.database import engine

# TODO (Scaling/Concurrency):
# APScheduler + SQLAlchemyJobStore works correctly for a single backend process.
# The moment we scale to more than one instance (for uptime/load), this must be
# moved to a distributed job store (e.g. Redis) or add leader election so two 
# instances can't both fire the same retry simultaneously.

jobstores = {
    'default': SQLAlchemyJobStore(engine=engine)
}

scheduler = BackgroundScheduler(jobstores=jobstores)

def start_scheduler():
    from app.jobs import reconciliation_sweep_job, detect_bank_outages_job
    
    # Add reconciliation sweep to run every 15 minutes
    scheduler.add_job(
        reconciliation_sweep_job,
        'interval',
        minutes=15,
        id='reconciliation_sweep',
        replace_existing=True
    )
    
    # Add bank outage detector to run every 5 minutes
    scheduler.add_job(
        detect_bank_outages_job,
        'interval',
        minutes=5,
        id='detect_bank_outages',
        replace_existing=True
    )
    
    scheduler.start()
