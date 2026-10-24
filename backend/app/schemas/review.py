"""Human-in-the-loop review models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewType = Literal["answer", "entity", "relation"]
ReviewStatus = Literal["pending", "approved", "edited", "rejected"]


class ReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    item_type: str
    status: str
    reference_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    confidence: float | None = None
    reviewer: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class ReviewList(BaseModel):
    total: int
    items: list[ReviewItemOut]


class ReviewDecision(BaseModel):
    comment: str | None = Field(None, max_length=2000)


class ReviewEdit(ReviewDecision):
    """Approve with changes.

    - answer:   {"final_answer": "..."}
    - entity:   {"entity": {"name": "...", "label": "..."}}
    - relation: {"relation": {"predicate": "..."}, "subject_entity": {...}, "object_entity": {...}}
    """

    payload: dict[str, Any]


class ReviewStats(BaseModel):
    pending: int = 0
    approved: int = 0
    edited: int = 0
    rejected: int = 0
    pending_by_type: dict[str, int] = Field(default_factory=dict)


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    actor: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
