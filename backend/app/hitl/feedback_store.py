"""Persist user feedback; negative feedback can send an answer back for human review."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Feedback, QueryLog
from app.hitl import review_queue
from app.hitl.policies import HITLPolicy
from app.schemas.feedback import FeedbackCreate


def add_feedback(db: Session, data: FeedbackCreate, policy: HITLPolicy) -> tuple[Feedback, bool]:
    log = db.get(QueryLog, data.query_id)
    if log is None:
        raise NotFoundError(f"Query {data.query_id} not found")
    feedback = Feedback(query_id=data.query_id, rating=data.rating, comment=data.comment, user=data.user)
    db.add(feedback)

    sent_to_review = False
    if (
        data.rating < 0
        and policy.negative_feedback_to_review
        and log.status == "answered"
        and not review_queue.has_pending(db, "answer", log.id)
    ):
        item = review_queue.enqueue(
            db, "answer",
            payload={"query": log.query, "draft_answer": log.answer, "contexts": log.contexts,
                     "guard_flags": log.guard_flags, "confidence": log.confidence,
                     "user_feedback": data.comment},
            reason="User marked the answer as not helpful" + (f": {data.comment}" if data.comment else ""),
            confidence=log.confidence,
            reference_id=log.id,
        )
        log.review_id = item.id
        sent_to_review = True
    db.flush()
    return feedback, sent_to_review


def list_feedback(db: Session, limit: int = 100, rating: int | None = None) -> list[Feedback]:
    stmt = select(Feedback)
    if rating is not None:
        stmt = stmt.where(Feedback.rating == rating)
    return list(db.scalars(stmt.order_by(Feedback.created_at.desc()).limit(limit)).all())


def summary(db: Session) -> dict:
    counts = dict(db.execute(select(Feedback.rating, func.count()).group_by(Feedback.rating)).all())
    positive, negative = counts.get(1, 0), counts.get(-1, 0)
    total = positive + negative
    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "positive_rate": round(positive / total, 3) if total else None,
        "recent_negative": list_feedback(db, limit=10, rating=-1),
    }
