"""Human-in-the-loop review endpoints (reviewer API key required)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_approval_handler
from app.core.security import require_reviewer
from app.db.session import get_db
from app.hitl import review_queue
from app.hitl.approval_handler import ApprovalHandler
from app.schemas.review import (
    AuditEventOut, ReviewDecision, ReviewEdit, ReviewItemOut, ReviewList, ReviewStats, ReviewType,
)
from app.services.audit_service import list_events

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(require_reviewer)])


@router.get("/pending", response_model=ReviewList)
def pending(
    item_type: ReviewType | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewList:
    total, items = review_queue.list_items(db, "pending", item_type, limit, offset)
    return ReviewList(total=total, items=[ReviewItemOut.model_validate(i) for i in items])


@router.get("/history", response_model=ReviewList)
def history(
    status: str = Query("reviewed", description="reviewed (all decided) | approved | edited | rejected"),
    item_type: ReviewType | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ReviewList:
    total, items = review_queue.list_items(db, status, item_type, limit)
    return ReviewList(total=total, items=[ReviewItemOut.model_validate(i) for i in items])


@router.get("/stats", response_model=ReviewStats)
def stats(db: Session = Depends(get_db)) -> ReviewStats:
    return ReviewStats(**review_queue.stats(db))


@router.get("/audit", response_model=list[AuditEventOut])
def audit(
    limit: int = Query(100, ge=1, le=1000),
    event_type: str | None = Query(None, description="Prefix, e.g. 'review' or 'query.blocked'"),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    return [AuditEventOut.model_validate(e) for e in list_events(db, limit, event_type)]


@router.get("/{item_id}", response_model=ReviewItemOut)
def get_item(item_id: str, db: Session = Depends(get_db)) -> ReviewItemOut:
    return ReviewItemOut.model_validate(review_queue.get(db, item_id))


@router.post("/{item_id}/approve", response_model=ReviewItemOut)
def approve(
    item_id: str,
    body: ReviewDecision | None = None,
    reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
    handler: ApprovalHandler = Depends(get_approval_handler),
) -> ReviewItemOut:
    item = handler.approve(db, review_queue.get(db, item_id), reviewer, body.comment if body else None)
    db.commit()
    return ReviewItemOut.model_validate(item)


@router.post("/{item_id}/edit", response_model=ReviewItemOut)
def edit(
    item_id: str,
    body: ReviewEdit,
    reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
    handler: ApprovalHandler = Depends(get_approval_handler),
) -> ReviewItemOut:
    """Approve with corrections (see ReviewEdit for the payload shape per item type)."""
    item = handler.approve(db, review_queue.get(db, item_id), reviewer, body.comment, edits=body.payload)
    db.commit()
    return ReviewItemOut.model_validate(item)


@router.post("/{item_id}/reject", response_model=ReviewItemOut)
def reject(
    item_id: str,
    body: ReviewDecision | None = None,
    reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
    handler: ApprovalHandler = Depends(get_approval_handler),
) -> ReviewItemOut:
    item = handler.reject(db, review_queue.get(db, item_id), reviewer, body.comment if body else None)
    db.commit()
    return ReviewItemOut.model_validate(item)
