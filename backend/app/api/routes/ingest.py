"""Document ingestion endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_ingest_service
from app.db.session import get_db
from app.schemas.ingest import IngestResponse, IngestTextRequest, IngestUrlRequest
from app.services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _parse_metadata(metadata: str | None) -> dict:
    if not metadata:
        return {}
    try:
        value = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"metadata must be a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return value


@router.post("/file", response_model=IngestResponse)
def ingest_file(
    file: UploadFile = File(...),
    metadata: str | None = Form(None, description='Optional JSON object, e.g. {"team": "legal"}'),
    db: Session = Depends(get_db),
    service: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
    data = file.file.read()
    return service.ingest_file(db, file.filename, data, file.content_type, _parse_metadata(metadata))


@router.post("/files", response_model=list[IngestResponse])
def ingest_files(
    files: list[UploadFile] = File(...),
    metadata: str | None = Form(None),
    db: Session = Depends(get_db),
    service: IngestService = Depends(get_ingest_service),
) -> list[IngestResponse]:
    meta = _parse_metadata(metadata)
    return [service.ingest_file(db, f.filename, f.file.read(), f.content_type, meta) for f in files]


@router.post("/text", response_model=IngestResponse)
def ingest_text(
    body: IngestTextRequest,
    db: Session = Depends(get_db),
    service: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
    return service.ingest_text(db, body.text, body.title, body.metadata)


@router.post("/url", response_model=IngestResponse)
def ingest_url(
    body: IngestUrlRequest,
    db: Session = Depends(get_db),
    service: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
    return service.ingest_url(db, str(body.url), body.metadata)
