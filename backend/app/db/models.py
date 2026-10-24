"""ORM models: Document, QueryLog, ReviewItem, Feedback, AuditLog."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """Registry of ingested documents (drives per-document metadata in the UI)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(2048))  # stored path, URL or "text"
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    num_pages: Mapped[int] = mapped_column(Integer, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0)
    num_entities: Mapped[int] = mapped_column(Integer, default=0)
    num_relations: Mapped[int] = mapped_column(Integer, default=0)
    pending_review: Mapped[int] = mapped_column(Integer, default=0)
    # processing | indexed | indexed_pending_review | blocked | failed
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    pii_redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QueryLog(Base):
    """Every question asked, with the answer, guard results and retrieved context."""

    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query: Mapped[str] = mapped_column(Text)
    sanitized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # answered | pending_review | blocked | rejected
    status: Mapped[str] = mapped_column(String(32), index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # what the user sees
    draft_answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # raw LLM output (post-guard)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    contexts: Mapped[list] = mapped_column(JSON, default=list)
    matched_entities: Mapped[list] = mapped_column(JSON, default=list)
    guard_flags: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[dict] = mapped_column(JSON, default=dict)
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ReviewItem(Base):
    """Human-in-the-loop queue: answers, entities and relations awaiting a decision."""

    __tablename__ = "review_items"
    __table_args__ = (Index("ix_review_status_type", "status", "item_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    item_type: Mapped[str] = mapped_column(String(16))  # answer | entity | relation
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | edited | rejected
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # query_id or doc_id
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query_id: Mapped[str] = mapped_column(String(36), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1 = helpful, -1 = not helpful
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(100), default="system")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
