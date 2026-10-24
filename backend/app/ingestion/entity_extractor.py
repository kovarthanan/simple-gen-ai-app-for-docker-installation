"""LLM-based entity and relation extraction with confidence scores."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.graph.base import Entity, Relation, normalize_key, safe_label, safe_rel_type
from app.ingestion.chunker import Chunk
from app.llm.client import LLMClient, extract_json
from app.llm.prompts import (
    ENTITY_EXTRACTION_PROMPT,
    ENTITY_EXTRACTION_SYSTEM,
    QUERY_ENTITY_PROMPT,
    QUERY_ENTITY_SYSTEM,
)

logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clamp(value, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


class EntityExtractor:
    def __init__(self, llm: LLMClient, entity_types: list[str], max_chars_per_call: int = 6000):
        self.llm = llm
        self.entity_types = entity_types
        self._type_lookup = {t.lower(): t for t in entity_types}
        self.max_chars = max_chars_per_call
        self.system_prompt = ENTITY_EXTRACTION_SYSTEM.replace("{types}", ", ".join(entity_types))

    def _normalize_type(self, value: str | None) -> str:
        if not value:
            return "Other"
        return self._type_lookup.get(str(value).strip().lower(), "Other")

    def _windows(self, chunks: list[Chunk]) -> list[list[Chunk]]:
        """Group consecutive chunks into windows of at most max_chars."""
        windows: list[list[Chunk]] = []
        current: list[Chunk] = []
        size = 0
        for chunk in chunks:
            if current and size + len(chunk.text) > self.max_chars:
                windows.append(current)
                current, size = [], 0
            current.append(chunk)
            size += len(chunk.text)
        if current:
            windows.append(current)
        return windows

    def extract(self, chunks: list[Chunk], doc_id: str) -> ExtractionResult:
        result = ExtractionResult()
        entities: dict[str, Entity] = {}
        relations: dict[tuple[str, str, str], Relation] = {}

        for window in self._windows(chunks):
            text = "\n\n".join(c.text for c in window)
            try:
                response = self.llm.complete(
                    ENTITY_EXTRACTION_PROMPT.format(text=text), system=self.system_prompt, max_tokens=2048
                )
                data = extract_json(response.text)
            except Exception as exc:
                logger.warning("Entity extraction failed for a window of doc %s: %s", doc_id, exc)
                result.warnings.append(f"Entity extraction failed for part of the document: {exc}")
                continue

            def chunk_ids_for(name: str) -> list[str]:
                needle = name.lower()
                hits = [c.id for c in window if needle in c.text.lower()]
                return hits or [c.id for c in window]

            for raw in data.get("entities") or []:
                if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
                    continue
                name = str(raw["name"]).strip()[:200]
                ent = Entity(
                    name=name,
                    label=safe_label(self._normalize_type(raw.get("type"))),
                    confidence=_clamp(raw.get("confidence")),
                    doc_ids=[doc_id],
                    chunk_ids=chunk_ids_for(name),
                )
                existing = entities.get(ent.key)
                if existing is None:
                    entities[ent.key] = ent
                else:
                    existing.confidence = max(existing.confidence, ent.confidence)
                    existing.chunk_ids = sorted(set(existing.chunk_ids) | set(ent.chunk_ids))
                    if existing.label == "Other":
                        existing.label = ent.label

            for raw in data.get("relations") or []:
                if not isinstance(raw, dict):
                    continue
                subj = str(raw.get("subject", "")).strip()[:200]
                obj = str(raw.get("object", "")).strip()[:200]
                if not subj or not obj or normalize_key(subj) == normalize_key(obj):
                    continue
                conf = _clamp(raw.get("confidence"))
                # make sure both endpoints exist as entities
                for name in (subj, obj):
                    if normalize_key(name) not in entities:
                        entities[normalize_key(name)] = Entity(
                            name=name, label="Other", confidence=conf, doc_ids=[doc_id], chunk_ids=chunk_ids_for(name)
                        )
                rel = Relation(
                    subject=entities[normalize_key(subj)].name,
                    predicate=safe_rel_type(raw.get("predicate")),
                    object=entities[normalize_key(obj)].name,
                    confidence=conf,
                    doc_id=doc_id,
                    chunk_ids=sorted(set(chunk_ids_for(subj)) & set(chunk_ids_for(obj))) or [c.id for c in window],
                )
                existing_rel = relations.get(rel.key)
                if existing_rel is None:
                    relations[rel.key] = rel
                else:
                    existing_rel.confidence = max(existing_rel.confidence, rel.confidence)

        for rel in relations.values():
            rel.subject_label = entities[normalize_key(rel.subject)].label
            rel.object_label = entities[normalize_key(rel.object)].label
        result.entities = list(entities.values())
        result.relations = list(relations.values())
        return result

    def extract_query_entities(self, query: str) -> list[str]:
        response = self.llm.complete(
            QUERY_ENTITY_PROMPT.format(query=query), system=QUERY_ENTITY_SYSTEM, max_tokens=200
        )
        data = extract_json(response.text)
        names = [str(n).strip() for n in data.get("entities") or [] if str(n).strip()]
        return names[:6]
