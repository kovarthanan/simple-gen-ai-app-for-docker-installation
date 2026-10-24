"""Query request/response models and retrieval result models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    top_k: int | None = Field(None, ge=1, le=50, description="Vector hits to retrieve")
    graph_depth: int | None = Field(None, ge=1, le=3, description="Hops to expand in the knowledge graph")
    graph_limit: int | None = Field(None, ge=1, le=200, description="Max graph facts to retrieve")
    final_top_k: int | None = Field(None, ge=1, le=50, description="Context items sent to the LLM after fusion")
    use_vector: bool = True
    use_graph: bool = True
    doc_ids: list[str] | None = Field(None, description="Restrict retrieval to these documents")
    user: str | None = Field(None, max_length=128)


class VectorHit(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float
    source: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphFact(BaseModel):
    subject: str
    subject_label: str | None = None
    predicate: str
    object: str
    object_label: str | None = None
    confidence: float = 1.0
    hops: int = 1
    doc_ids: list[str] = Field(default_factory=list)

    def as_text(self) -> str:
        s = f"{self.subject} ({self.subject_label})" if self.subject_label else self.subject
        o = f"{self.object} ({self.object_label})" if self.object_label else self.object
        return f"{s} -[{self.predicate}]-> {o}"


class ContextItem(BaseModel):
    """One piece of context after fusion: either a vector chunk or a graph fact."""

    id: str
    origin: Literal["vector", "graph"]
    content: str
    score: float = 0.0  # fused score
    rank: int = 0  # final rank after fusion (1-based)
    source_rank: int = 0  # rank inside its own retriever
    source_score: float = 0.0  # similarity (vector) or confidence (graph)
    citation: int | None = None  # number used in the prompt, e.g. [3]
    cited: bool = False  # did the answer cite it?
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardFlag(BaseModel):
    guard: str
    stage: str  # input | output | ingest
    passed: bool
    action: str  # allow | redact | flag | block
    reason: str | None = None
    score: float | None = None


class QueryResponse(BaseModel):
    query_id: str
    status: Literal["answered", "pending_review", "blocked", "rejected"]
    answer: str | None = None
    message: str | None = None
    confidence: float | None = None
    groundedness: float | None = None
    citations: list[int] = Field(default_factory=list)
    contexts: list[ContextItem] = Field(default_factory=list)
    matched_entities: list[str] = Field(default_factory=list)
    guard_flags: list[GuardFlag] = Field(default_factory=list)
    latency_ms: dict[str, float] = Field(default_factory=dict)
    review_id: str | None = None
    reviewed: bool = False
    created_at: datetime | None = None


class QueryHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    query: str
    status: str
    confidence: float | None = None
    groundedness: float | None = None
    reviewed: bool = False
    created_at: datetime
