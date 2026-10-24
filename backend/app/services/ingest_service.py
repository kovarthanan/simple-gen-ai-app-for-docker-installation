"""Ingestion orchestration: document registry, pipeline run, review queue, audit trail."""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.exceptions import AppError, GuardrailViolation, NotFoundError, StoreError
from app.core.logging import get_logger
from app.db.models import Document
from app.graph.base import GraphStore
from app.guardrails.runner import GuardReport
from app.hitl import review_queue
from app.hitl.notifications import Notifier
from app.ingestion.loaders import LoadedDocument, LoadedPage, load_bytes, load_url
from app.ingestion.pipeline import IngestionPipeline
from app.schemas.document import DocumentDeleteResponse
from app.schemas.ingest import IngestResponse
from app.schemas.query import GuardFlag
from app.services.audit_service import log_event
from app.vectorstore.base import VectorStore

logger = get_logger(__name__)


def safe_filename(name: str | None) -> str:
    name = Path(name or "upload").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "upload"
    return name[:200]


class IngestService:
    def __init__(self, settings: Settings, pipeline: IngestionPipeline, vector_store: VectorStore,
                 graph_store: GraphStore, notifier: Notifier):
        self.settings = settings
        self.pipeline = pipeline
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.notifier = notifier

    # -- entry points --------------------------------------------------------------
    def ingest_file(self, db: Session, filename: str | None, data: bytes, content_type: str | None = None,
                    metadata: dict[str, Any] | None = None, actor: str = "api") -> IngestResponse:
        filename = safe_filename(filename)
        file_report = self.pipeline.guardrails.run_ingest_file(filename, len(data))
        if file_report.blocked:
            self._log_blocked(db, filename, file_report, actor)
            raise GuardrailViolation(file_report.block_reason or "File rejected",
                                     details=[f.model_dump() for f in file_report.flags()])
        doc = load_bytes(filename, data, content_type)
        doc_id = str(uuid.uuid4())
        doc.source = self._save_raw(doc_id, filename, data)
        return self._ingest(db, doc_id, doc, len(data), metadata, file_report.flags(), actor)

    def ingest_text(self, db: Session, text: str, title: str, metadata: dict[str, Any] | None = None,
                    actor: str = "api") -> IngestResponse:
        doc = LoadedDocument(filename=safe_filename(title), pages=[LoadedPage(text=text)],
                             content_type="text/plain", source="text")
        return self._ingest(db, str(uuid.uuid4()), doc, len(text.encode()), metadata, [], actor)

    def ingest_url(self, db: Session, url: str, metadata: dict[str, Any] | None = None,
                   actor: str = "api") -> IngestResponse:
        max_bytes = int(self.pipeline.guardrails.policy["ingest"].get("max_file_mb", 20) * 1024 * 1024)
        doc, size = load_url(url, allow_private=self.settings.allow_private_urls, max_bytes=max_bytes)
        doc.filename = safe_filename(doc.filename)
        return self._ingest(db, str(uuid.uuid4()), doc, size, metadata, [], actor)

    # -- core ----------------------------------------------------------------------------
    def _ingest(self, db: Session, doc_id: str, doc: LoadedDocument, size: int, metadata: dict[str, Any] | None,
                flags: list[GuardFlag], actor: str) -> IngestResponse:
        record = Document(id=doc_id, filename=doc.filename, source=doc.source, content_type=doc.content_type,
                          size_bytes=size, num_pages=len(doc.pages), status="processing", meta=metadata or {})
        db.add(record)
        db.commit()

        try:
            result = self.pipeline.run(doc, doc_id, metadata)
        except AppError as exc:
            record.status = "blocked" if isinstance(exc, GuardrailViolation) else "failed"
            record.warnings = [exc.message]
            log_event(db, f"ingest.{record.status}", actor, doc_id=doc_id, filename=doc.filename, reason=exc.message)
            db.commit()
            self._cleanup_vectors(doc_id)
            raise
        except Exception as exc:
            logger.exception("Ingestion failed for %s", doc.filename)
            record.status = "failed"
            record.warnings = [str(exc)]
            log_event(db, "ingest.failed", actor, doc_id=doc_id, filename=doc.filename, reason=str(exc))
            db.commit()
            self._cleanup_vectors(doc_id)
            raise StoreError(f"Ingestion failed: {type(exc).__name__}: {exc}") from exc

        for ent in result.review_entities:
            review_queue.enqueue(
                db, "entity",
                payload={"entity": asdict(ent), "doc_id": doc_id, "filename": doc.filename},
                reason=f"Entity confidence {ent.confidence:.2f} is below the auto-approve threshold",
                confidence=ent.confidence, reference_id=doc_id,
            )
        for rel, subj, obj in result.review_relations:
            review_queue.enqueue(
                db, "relation",
                payload={"relation": asdict(rel), "subject_entity": asdict(subj), "object_entity": asdict(obj),
                         "doc_id": doc_id, "filename": doc.filename},
                reason=f"Relation confidence {rel.confidence:.2f} or an endpoint needs review",
                confidence=rel.confidence, reference_id=doc_id,
            )

        pending = len(result.review_entities) + len(result.review_relations)
        all_flags = flags + (result.content_report.flags() if result.content_report else [])
        record.num_chunks = result.num_chunks
        record.num_entities = len(result.auto_entities)
        record.num_relations = len(result.auto_relations)
        record.pending_review = pending
        record.pii_redacted = result.pii_redacted
        record.warnings = result.warnings
        record.status = "indexed_pending_review" if pending else "indexed"
        log_event(db, "ingest.indexed", actor, doc_id=doc_id, filename=doc.filename, chunks=result.num_chunks,
                  auto_approved=len(result.auto_entities) + len(result.auto_relations),
                  pending_review=pending, pii_redacted=result.pii_redacted)
        db.commit()

        if pending:
            self.notifier.notify(f"{pending} knowledge-graph item(s) from '{doc.filename}' are waiting for review")

        return IngestResponse(
            doc_id=doc_id, filename=doc.filename, status=record.status, num_pages=result.num_pages,
            num_chunks=result.num_chunks, entities_extracted=result.entities_extracted,
            relations_extracted=result.relations_extracted,
            auto_approved=len(result.auto_entities) + len(result.auto_relations),
            pending_review=pending, dropped=result.dropped, pii_redacted=result.pii_redacted,
            guard_flags=all_flags, warnings=result.warnings,
        )

    # -- delete ----------------------------------------------------------------------
    def delete_document(self, db: Session, doc_id: str, actor: str = "api") -> DocumentDeleteResponse:
        record = db.get(Document, doc_id)
        if record is None:
            raise NotFoundError(f"Document {doc_id} not found")
        warnings = []
        for name, fn in (("vector store", self.vector_store.delete_by_doc),
                         ("knowledge graph", self.graph_store.delete_by_doc)):
            try:
                fn(doc_id)
            except Exception as exc:
                warnings.append(f"Could not delete from {name}: {exc}")
        removed = review_queue.delete_pending_for_reference(db, doc_id)
        if record.source and record.source not in {"text"} and not record.source.startswith("http"):
            try:
                Path(record.source).unlink(missing_ok=True)
            except OSError as exc:
                warnings.append(f"Could not delete stored file: {exc}")
        db.delete(record)
        log_event(db, "document.deleted", actor, doc_id=doc_id, filename=record.filename, warnings=warnings)
        db.commit()
        return DocumentDeleteResponse(doc_id=doc_id, deleted=True, reviews_removed=removed, warnings=warnings)

    # -- helpers ----------------------------------------------------------------------
    def _save_raw(self, doc_id: str, filename: str, data: bytes) -> str:
        try:
            folder = Path(self.settings.upload_dir)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{doc_id}_{filename}"
            path.write_bytes(data)
            return str(path)
        except OSError as exc:
            logger.warning("Could not store raw upload: %s", exc)
            return "upload"

    def _cleanup_vectors(self, doc_id: str) -> None:
        try:
            self.vector_store.delete_by_doc(doc_id)
        except Exception:
            pass

    @staticmethod
    def _log_blocked(db: Session, filename: str, report: GuardReport, actor: str) -> None:
        log_event(db, "ingest.blocked", actor, filename=filename, reason=report.block_reason)
        db.commit()
