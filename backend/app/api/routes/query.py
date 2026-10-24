"""Question answering endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_rag_service
from app.db.session import get_db
from app.schemas.query import QueryHistoryItem, QueryRequest, QueryResponse
from app.services.rag_service import RAGService

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def ask(
    body: QueryRequest,
    db: Session = Depends(get_db),
    service: RAGService = Depends(get_rag_service),
) -> QueryResponse:
    """Input guardrails -> hybrid retrieval -> LLM -> output guardrails -> answer or human review."""
    return await service.answer(db, body)


@router.get("/history", response_model=list[QueryHistoryItem])
def history(
    limit: int = Query(50, ge=1, le=500),
    status: str | None = Query(None, description="answered | pending_review | blocked | rejected"),
    db: Session = Depends(get_db),
    service: RAGService = Depends(get_rag_service),
) -> list[QueryHistoryItem]:
    return [QueryHistoryItem.model_validate(q) for q in service.history(db, limit, status)]


@router.get("/{query_id}", response_model=QueryResponse)
def get_query(
    query_id: str,
    db: Session = Depends(get_db),
    service: RAGService = Depends(get_rag_service),
) -> QueryResponse:
    """Poll this after a pending_review answer to see the reviewed result."""
    return service.get_result(db, query_id)
