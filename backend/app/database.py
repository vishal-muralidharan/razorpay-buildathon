"""
Database engine and session configuration.

Uses SQLite by default (fast to set up, zero external dependencies -
ideal for a buildathon demo). Swap DATABASE_URL to a Postgres DSN
(e.g. postgresql+psycopg2://user:pass@host/db) for production without
changing any other code, since all access goes through SQLAlchemy.
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
