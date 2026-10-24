"""User feedback endpoints (thumbs up/down on answers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_hitl_policy
from app.core.security import require_reviewer
from app.db.session import get_db
from app.hitl import feedback_store
from app.hitl.policies import HITLPolicy
from app.schemas.feedback import FeedbackCreate, FeedbackCreated, FeedbackOut, FeedbackSummary
from app.services.audit_service import log_event

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackCreated, status_code=201)
def submit(
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    policy: HITLPolicy = Depends(get_hitl_policy),
) -> FeedbackCreated:
    feedback, sent = feedback_store.add_feedback(db, body, policy)
    log_event(db, "feedback.submitted", body.user or "user", query_id=body.query_id,
              rating=body.rating, sent_to_review=sent)
    db.commit()
    return FeedbackCreated(**FeedbackOut.model_validate(feedback).model_dump(), sent_to_review=sent)


@router.get("/summary", response_model=FeedbackSummary)
def summary(db: Session = Depends(get_db)) -> FeedbackSummary:
    return FeedbackSummary.model_validate(feedback_store.summary(db), from_attributes=True)


@router.get("", response_model=list[FeedbackOut], dependencies=[Depends(require_reviewer)])
def list_all(
    limit: int = Query(100, ge=1, le=1000),
    rating: int | None = Query(None, description="1 or -1"),
    db: Session = Depends(get_db),
) -> list[FeedbackOut]:
    return [FeedbackOut.model_validate(f) for f in feedback_store.list_feedback(db, limit, rating)]
