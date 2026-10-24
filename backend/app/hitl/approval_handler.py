"""Apply reviewer decisions: write approved entities/relations to the graph, publish answers."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, StoreError
from app.core.logging import get_logger
from app.db.models import Document, QueryLog, ReviewItem, utcnow
from app.graph.base import Entity, GraphStore, Relation, safe_label, safe_rel_type
from app.services.audit_service import log_event

logger = get_logger(__name__)


def _merge_payload(base: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in edits.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _entity_from(data: dict[str, Any]) -> Entity:
    return Entity(
        name=str(data["name"]).strip(),
        label=safe_label(data.get("label")),
        confidence=1.0,  # human-verified
        doc_ids=list(data.get("doc_ids") or []),
        chunk_ids=list(data.get("chunk_ids") or []),
        verified=True,
    )


class ApprovalHandler:
    def __init__(self, graph_store: GraphStore):
        self.graph = graph_store

    def approve(self, db: Session, item: ReviewItem, reviewer: str, comment: str | None = None,
                edits: dict[str, Any] | None = None) -> ReviewItem:
        if item.status != "pending":
            raise ConflictError(f"Review item is already {item.status}")
        payload = _merge_payload(item.payload, edits) if edits else item.payload

        try:
            if item.item_type == "entity":
                self.graph.upsert_entities([_entity_from(payload["entity"])])
            elif item.item_type == "relation":
                rel = payload["relation"]
                subject = _entity_from(payload["subject_entity"])
                obj = _entity_from(payload["object_entity"])
                self.graph.upsert_entities([subject, obj])
                self.graph.upsert_relations([
                    Relation(
                        subject=subject.name, object=obj.name,
                        predicate=safe_rel_type(rel.get("predicate")),
                        subject_label=subject.label, object_label=obj.label,
                        confidence=1.0, doc_id=rel.get("doc_id"),
                        chunk_ids=list(rel.get("chunk_ids") or []), verified=True,
                    )
                ])
            elif item.item_type == "answer":
                log = db.get(QueryLog, item.reference_id) if item.reference_id else None
                if log is not None:
                    log.answer = payload.get("final_answer") or payload.get("draft_answer")
                    log.status = "answered"
                    log.reviewed = True
                    log.message = "Reviewed and approved by a human."
        except (KeyError, TypeError) as exc:
            raise ConflictError(f"Review payload is missing fields: {exc}") from exc
        except Exception as exc:
            raise StoreError(f"Could not apply approval: {exc}") from exc

        item.payload = payload
        item.status = "edited" if edits else "approved"
        self._finish(db, item, reviewer, comment)
        log_event(db, f"review.{item.status}", reviewer,
                  review_id=item.id, item_type=item.item_type, reference_id=item.reference_id, comment=comment)
        return item

    def reject(self, db: Session, item: ReviewItem, reviewer: str, comment: str | None = None) -> ReviewItem:
        if item.status != "pending":
            raise ConflictError(f"Review item is already {item.status}")
        if item.item_type == "answer" and item.reference_id:
            log = db.get(QueryLog, item.reference_id)
            if log is not None:
                log.status = "rejected"
                log.answer = None
                log.reviewed = True
                log.message = "A reviewer rejected this answer" + (f": {comment}" if comment else ".")
        item.status = "rejected"
        self._finish(db, item, reviewer, comment)
        log_event(db, "review.rejected", reviewer,
                  review_id=item.id, item_type=item.item_type, reference_id=item.reference_id, comment=comment)
        return item

    @staticmethod
    def _finish(db: Session, item: ReviewItem, reviewer: str, comment: str | None) -> None:
        item.reviewer = reviewer
        item.reviewer_comment = comment
        item.reviewed_at = utcnow()
        if item.item_type in {"entity", "relation"} and item.reference_id:
            doc = db.get(Document, item.reference_id)
            if doc is not None:
                doc.pending_review = max(0, doc.pending_review - 1)
                if item.status != "rejected":
                    if item.item_type == "entity":
                        doc.num_entities += 1
                    else:
                        doc.num_relations += 1
                if doc.pending_review == 0 and doc.status == "indexed_pending_review":
                    doc.status = "indexed"
