"""Document models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    filename: str
    source: str
    content_type: str | None = None
    size_bytes: int = 0
    num_pages: int = 0
    num_chunks: int = 0
    num_entities: int = 0
    num_relations: int = 0
    pending_review: int = 0
    status: str
    pii_redacted: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="meta")
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class DocumentList(BaseModel):
    total: int
    items: list[DocumentOut]


class DocumentDeleteResponse(BaseModel):
    doc_id: str
    deleted: bool
    reviews_removed: int = 0
    warnings: list[str] = Field(default_factory=list)
