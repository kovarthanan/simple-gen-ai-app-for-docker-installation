"""Ingestion request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.query import GuardFlag


class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    title: str = Field("pasted-text.txt", max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestUrlRequest(BaseModel):
    url: HttpUrl
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    num_pages: int = 0
    num_chunks: int = 0
    entities_extracted: int = 0
    relations_extracted: int = 0
    auto_approved: int = 0  # written straight to the knowledge graph
    pending_review: int = 0  # waiting in the human review queue
    dropped: int = 0  # below the minimum confidence
    pii_redacted: bool = False
    guard_flags: list[GuardFlag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
