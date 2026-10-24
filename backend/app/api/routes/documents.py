"""Document registry endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_ingest_service
from app.core.exceptions import NotFoundError
from app.db.models import Document
from app.db.session import get_db
from app.schemas.document import DocumentDeleteResponse, DocumentList, DocumentOut
from app.services.ingest_service import IngestService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentList)
def list_documents(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    db: Session = Depends(get_db),
) -> DocumentList:
    stmt = select(Document)
    if status:
        stmt = stmt.where(Document.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    docs = db.scalars(stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit)).all()
    return DocumentList(total=total, items=[DocumentOut.model_validate(d) for d in docs])


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, db: Session = Depends(get_db)) -> DocumentOut:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise NotFoundError(f"Document {doc_id} not found")
    return DocumentOut.model_validate(doc)


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    service: IngestService = Depends(get_ingest_service),
) -> DocumentDeleteResponse:
    """Removes the document's vectors, its graph facts (unless shared with other docs) and pending reviews."""
    return service.delete_document(db, doc_id)
