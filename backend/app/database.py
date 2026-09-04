"""
Database engine and session configuration.

TODO (Production Database):
Uses SQLite by default (fast to set up, zero external dependencies). 
However, for real concurrent webhook traffic, we must swap to Postgres 
(change DATABASE_URL) to ensure row-level locking (`with_for_update`) 
is properly enforced to keep the audit-ledger writes correctly serialized.
No schema changes are needed; this is a standard Alembic-driven swap.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mandate_resurrection.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
