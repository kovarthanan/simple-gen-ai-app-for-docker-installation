"""Metadata models for the vector DB and knowledge graph dashboards."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LabelCount(BaseModel):
    label: str
    count: int


class TypeCount(BaseModel):
    type: str
    count: int


class EntityDegree(BaseModel):
    entity: str
    label: str | None = None
    degree: int


class DocumentStat(BaseModel):
    doc_id: str
    filename: str
    status: str
    num_chunks: int
    num_entities: int
    num_relations: int
    pending_review: int
    created_at: datetime


class VectorMetadata(BaseModel):
    available: bool = True
    error: str | None = None
    collection: str
    exists: bool = False
    vectors_count: int = 0
    indexed_vectors_count: int | None = None
    dimension: int | None = None
    distance: str | None = None
    status: str | None = None
    segments_count: int | None = None
    payload_fields: list[str] = Field(default_factory=list)
    embedding_model: str
    documents: list[DocumentStat] = Field(default_factory=list)


class GraphMetadata(BaseModel):
    available: bool = True
    error: str | None = None
    total_nodes: int = 0
    total_relationships: int = 0
    total_chunks_linked: int = 0
    verified_entities: int = 0
    isolated_nodes: int = 0
    node_labels: list[LabelCount] = Field(default_factory=list)
    relationship_types: list[TypeCount] = Field(default_factory=list)
    top_entities: list[EntityDegree] = Field(default_factory=list)
    property_keys: list[str] = Field(default_factory=list)


class SummaryMetadata(BaseModel):
    vector: VectorMetadata
    graph: GraphMetadata
    documents_total: int = 0
    chunks_total: int = 0
    queries_total: int = 0
    queries_by_status: dict[str, int] = Field(default_factory=dict)
    pending_reviews: int = 0
    reviews_by_type: dict[str, int] = Field(default_factory=dict)
    feedback_total: int = 0
    positive_feedback_rate: float | None = None
    last_ingested_at: datetime | None = None


class SubgraphNode(BaseModel):
    id: str
    name: str
    label: str | None = None


class SubgraphEdge(BaseModel):
    source: str
    target: str
    type: str
    confidence: float = 1.0


class Subgraph(BaseModel):
    nodes: list[SubgraphNode] = Field(default_factory=list)
    edges: list[SubgraphEdge] = Field(default_factory=list)
