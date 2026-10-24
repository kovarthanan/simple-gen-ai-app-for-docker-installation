"""Audit log of queries, guardrail decisions, ingestion and reviewer actions."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def log_event(db: Session, event_type: str, actor: str = "system", **details: Any) -> AuditLog:
    """Adds the event to the session; the caller's commit persists it with the rest of the work."""
    event = AuditLog(event_type=event_type, actor=actor or "system", details=details)
    db.add(event)
    return event


def list_events(db: Session, limit: int = 100, event_type: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog)
    if event_type:
        stmt = stmt.where(AuditLog.event_type.startswith(event_type))
    return list(db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit)).all())
