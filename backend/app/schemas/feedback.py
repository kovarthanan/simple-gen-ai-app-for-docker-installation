"""User feedback models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    query_id: str
    rating: Literal[1, -1]
    comment: str | None = Field(None, max_length=2000)
    user: str | None = Field(None, max_length=128)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    query_id: str
    rating: int
    comment: str | None = None
    user: str | None = None
    created_at: datetime


class FeedbackCreated(FeedbackOut):
    sent_to_review: bool = False


class FeedbackSummary(BaseModel):
    total: int = 0
    positive: int = 0
    negative: int = 0
    positive_rate: float | None = None
    recent_negative: list[FeedbackOut] = Field(default_factory=list)
