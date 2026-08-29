"""
Layer 4 - Cryptographic Decision Audit Ledger.

An append-only, hash-chained log, scoped per transaction. Each AuditLog row
stores hash = SHA256(prev_hash + step_name + payload_json + timestamp).
Because each row's hash depends on the previous row's hash, editing or
deleting any historical row breaks every hash computed after it - so
`verify_chain` can detect tampering without needing a real blockchain.

GENESIS_HASH is the prev_hash used for the first entry of any transaction's
chain.
"""
import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app import models

GENESIS_HASH = "0" * 64


def _compute_hash(prev_hash: str, step_name: str, payload_json: str, timestamp: datetime) -> str:
    raw = f"{prev_hash}|{step_name}|{payload_json}|{timestamp.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def log_step(db: Session, transaction_id: int, step_name: str, payload: dict) -> models.AuditLog:
    """Appends a new hash-chained audit row for this transaction and commits it."""
    last_entry = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.transaction_id == transaction_id)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    prev_hash = last_entry.hash if last_entry else GENESIS_HASH
    timestamp = datetime.utcnow()
    payload_json = json.dumps(payload, default=str, sort_keys=True)
    entry_hash = _compute_hash(prev_hash, step_name, payload_json, timestamp)

    entry = models.AuditLog(
        transaction_id=transaction_id,
        step_name=step_name,
        payload_json=payload_json,
        prev_hash=prev_hash,
        hash=entry_hash,
        timestamp=timestamp,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_chain(entries: list[models.AuditLog]) -> bool:
    """Recomputes every hash in order and checks it matches what's stored,
    and that each prev_hash correctly points at the prior row's hash."""
    expected_prev = GENESIS_HASH
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return False
        recomputed = _compute_hash(entry.prev_hash, entry.step_name, entry.payload_json, entry.timestamp)
        if recomputed != entry.hash:
            return False
        expected_prev = entry.hash
    return True
