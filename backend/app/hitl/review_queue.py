"""Review queue backed by the relational DB."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import ReviewItem


def enqueue(
    db: Session,
    item_type: str,
    payload: dict[str, Any],
    reason: str | None = None,
    confidence: float | None = None,
    reference_id: str | None = None,
) -> ReviewItem:
    item = ReviewItem(item_type=item_type, payload=payload, reason=reason,
                      confidence=confidence, reference_id=reference_id)
    db.add(item)
    db.flush()
    return item


def list_items(
    db: Session, status: str | None = "pending", item_type: str | None = None,
    limit: int = 50, offset: int = 0,
) -> tuple[int, list[ReviewItem]]:
    stmt = select(ReviewItem)
    if status == "reviewed":  # anything already decided
        stmt = stmt.where(ReviewItem.status != "pending")
    elif status:
        stmt = stmt.where(ReviewItem.status == status)
    if item_type:
        stmt = stmt.where(ReviewItem.item_type == item_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(ReviewItem.created_at.asc()).offset(offset).limit(limit)).all()
    return total, list(items)


def get(db: Session, item_id: str) -> ReviewItem:
    item = db.get(ReviewItem, item_id)
    if item is None:
        raise NotFoundError(f"Review item {item_id} not found")
    return item


def has_pending(db: Session, item_type: str, reference_id: str) -> bool:
    stmt = select(func.count()).where(
        ReviewItem.item_type == item_type,
        ReviewItem.reference_id == reference_id,
        ReviewItem.status == "pending",
    )
    return (db.scalar(stmt) or 0) > 0


def delete_pending_for_reference(db: Session, reference_id: str) -> int:
    items = db.scalars(
        select(ReviewItem).where(ReviewItem.reference_id == reference_id, ReviewItem.status == "pending")
    ).all()
    for item in items:
        db.delete(item)
    return len(items)


def stats(db: Session) -> dict[str, Any]:
    by_status = dict(db.execute(select(ReviewItem.status, func.count()).group_by(ReviewItem.status)).all())
    pending_by_type = dict(
        db.execute(
            select(ReviewItem.item_type, func.count())
            .where(ReviewItem.status == "pending")
            .group_by(ReviewItem.item_type)
        ).all()
    )
    return {
        "pending": by_status.get("pending", 0),
        "approved": by_status.get("approved", 0),
        "edited": by_status.get("edited", 0),
        "rejected": by_status.get("rejected", 0),
        "pending_by_type": pending_by_type,
    }
