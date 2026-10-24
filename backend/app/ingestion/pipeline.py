"""Ingestion pipeline:

load -> PII redaction -> content guards -> chunk -> embed -> Qdrant
                                                  -> extract entities/relations
                                                       -> high confidence: Neo4j
                                                       -> medium confidence: human review queue
                                                       -> low confidence: dropped
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.core.exceptions import GuardrailViolation, IngestionError
from app.core.logging import get_logger
from app.graph.base import Entity, GraphStore, Relation
from app.guardrails.base import GuardAction
from app.guardrails.runner import GuardrailRunner, GuardReport
from app.hitl.policies import HITLPolicy
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import Embedder
from app.ingestion.entity_extractor import EntityExtractor
from app.ingestion.loaders import LoadedDocument
from app.vectorstore.base import VectorRecord, VectorStore

logger = get_logger(__name__)

_RESERVED_PAYLOAD = {"chunk_id", "doc_id", "text", "source", "page", "chunk_index", "ingested_at"}


@dataclass
class PipelineResult:
    num_pages: int = 0
    num_chunks: int = 0
    entities_extracted: int = 0
    relations_extracted: int = 0
    auto_entities: list[Entity] = field(default_factory=list)
    auto_relations: list[Relation] = field(default_factory=list)
    review_entities: list[Entity] = field(default_factory=list)
    # (relation, subject entity, object entity) so a reviewer can approve it in one step
    review_relations: list[tuple[Relation, Entity, Entity]] = field(default_factory=list)
    dropped: int = 0
    pii_redacted: bool = False
    content_report: GuardReport | None = None
    warnings: list[str] = field(default_factory=list)


class IngestionPipeline:
    def __init__(self, settings: Settings, embedder: Embedder, vector_store: VectorStore,
                 graph_store: GraphStore, extractor: EntityExtractor, guardrails: GuardrailRunner,
                 hitl_policy: HITLPolicy):
        self.settings = settings
        self.embedder = embedder
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.extractor = extractor
        self.guardrails = guardrails
        self.hitl = hitl_policy

    def run(self, doc: LoadedDocument, doc_id: str, metadata: dict[str, Any] | None = None) -> PipelineResult:
        result = PipelineResult(num_pages=len(doc.pages))

        # 1. Guardrails: redact PII page by page, then check the content as a whole
        for page in doc.pages:
            page.text, pii_result = self.guardrails.sanitize_document_text(page.text)
            if pii_result is not None and pii_result.action == GuardAction.REDACT:
                result.pii_redacted = True
        report = self.guardrails.run_ingest_content(doc.full_text)
        result.content_report = report
        if report.blocked:
            raise GuardrailViolation(report.block_reason or "Document blocked by guardrails",
                                     details=[f.model_dump() for f in report.flags()])
        if "prompt_injection" in report.flagged_guards:
            result.warnings.append("Document contains text that looks like instructions to an AI; "
                                   "it was indexed but flagged.")

        # 2. Chunk + embed + store vectors
        chunks = chunk_document(doc_id, doc.pages, self.settings.chunk_size, self.settings.chunk_overlap,
                                base_metadata={"source": doc.filename})
        if not chunks:
            raise IngestionError("No text could be extracted from the document")
        result.num_chunks = len(chunks)

        vectors = self.embedder.embed([c.text for c in chunks])
        self.vector_store.ensure_collection(self.embedder.dimension)
        ingested_at = datetime.now(timezone.utc).isoformat()
        extra = {k: v for k, v in (metadata or {}).items() if k not in _RESERVED_PAYLOAD}
        self.vector_store.upsert([
            VectorRecord(
                id=chunk.id,
                vector=vector,
                payload={"chunk_id": chunk.id, "doc_id": doc_id, "text": chunk.text, "source": doc.filename,
                         "page": chunk.page, "chunk_index": chunk.index, "ingested_at": ingested_at, **extra},
            )
            for chunk, vector in zip(chunks, vectors)
        ])

        # 3. Knowledge graph extraction, routed by confidence
        extraction = self.extractor.extract(chunks, doc_id)
        result.warnings.extend(extraction.warnings)
        result.entities_extracted = len(extraction.entities)
        result.relations_extracted = len(extraction.relations)

        by_key = {e.key: e for e in extraction.entities}
        auto_keys: set[str] = set()
        dropped_keys: set[str] = set()
        for ent in extraction.entities:
            route = self.hitl.route_entity(ent)
            if route == "auto":
                result.auto_entities.append(ent)
                auto_keys.add(ent.key)
            elif route == "review":
                result.review_entities.append(ent)
            else:
                dropped_keys.add(ent.key)
                result.dropped += 1
        for rel in extraction.relations:
            route = self.hitl.route_relation(rel, auto_keys, dropped_keys)
            s_key, _, o_key = rel.key
            if route == "auto":
                result.auto_relations.append(rel)
            elif route == "review":
                result.review_relations.append((rel, by_key[s_key], by_key[o_key]))
            else:
                result.dropped += 1

        # 4. Write auto-approved items; if the graph is down, send them to review instead of losing them
        if result.auto_entities or result.auto_relations:
            try:
                self.graph_store.upsert_entities(result.auto_entities)
                self.graph_store.upsert_relations(result.auto_relations)
            except Exception as exc:
                logger.exception("Graph write failed for doc %s", doc_id)
                result.warnings.append(f"Knowledge graph write failed ({exc}); items were queued for review.")
                result.review_entities.extend(result.auto_entities)
                result.review_relations.extend(
                    (r, by_key[r.key[0]], by_key[r.key[2]]) for r in result.auto_relations
                )
                result.auto_entities, result.auto_relations = [], []
        return result
