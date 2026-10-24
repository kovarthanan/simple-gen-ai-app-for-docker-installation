"""Metadata endpoints for the vector DB / knowledge graph dashboard and graph explorer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_metadata_service
from app.db.session import get_db
from app.schemas.metadata import GraphMetadata, Subgraph, SummaryMetadata, VectorMetadata
from app.services.metadata_service import MetadataService

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/vector", response_model=VectorMetadata)
def vector_metadata(db: Session = Depends(get_db),
                    service: MetadataService = Depends(get_metadata_service)) -> VectorMetadata:
    return service.vector(db)


@router.get("/graph", response_model=GraphMetadata)
def graph_metadata(top_n: int = Query(10, ge=1, le=100),
                   service: MetadataService = Depends(get_metadata_service)) -> GraphMetadata:
    return service.graph(top_n=top_n)


@router.get("/summary", response_model=SummaryMetadata)
def summary(db: Session = Depends(get_db),
            service: MetadataService = Depends(get_metadata_service)) -> SummaryMetadata:
    return service.summary(db)


@router.get("/graph/subgraph", response_model=Subgraph)
def subgraph(
    limit: int = Query(100, ge=1, le=1000),
    entity: str | None = Query(None, description="Only edges touching this entity"),
    service: MetadataService = Depends(get_metadata_service),
) -> Subgraph:
    """Nodes and edges for the Streamlit graph explorer."""
    return service.subgraph(limit=limit, entity=entity)
