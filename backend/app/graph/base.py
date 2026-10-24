"""Knowledge-graph domain objects and the GraphStore interface."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

_WS = re.compile(r"\s+")


def normalize_key(name: str) -> str:
    """Stable identity for an entity: lower-cased, whitespace-collapsed name."""
    return _WS.sub(" ", name.strip()).lower()


def safe_label(label: str | None, default: str = "Other") -> str:
    """Neo4j labels can't be query parameters, so only allow [A-Za-z0-9_]."""
    if not label:
        return default
    parts = re.findall(r"[A-Za-z0-9]+", label)
    cleaned = "".join(p[:1].upper() + p[1:] for p in parts)
    if not cleaned or not cleaned[0].isalpha() or cleaned in {"Entity", "Chunk"}:
        return default
    return cleaned[:40]


def safe_rel_type(predicate: str | None, default: str = "RELATED_TO") -> str:
    if not predicate:
        return default
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", predicate.strip()).strip("_").upper()
    if not cleaned or not cleaned[0].isalpha() or cleaned == "MENTIONED_IN":
        return default
    return cleaned[:50]


@dataclass
class Entity:
    name: str
    label: str = "Other"
    confidence: float = 1.0
    doc_ids: list[str] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)
    verified: bool = False  # set when a human approved it

    @property
    def key(self) -> str:
        return normalize_key(self.name)


@dataclass
class Relation:
    subject: str
    predicate: str
    object: str
    subject_label: str = "Other"
    object_label: str = "Other"
    confidence: float = 1.0
    doc_id: str | None = None
    chunk_ids: list[str] = field(default_factory=list)
    verified: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return normalize_key(self.subject), self.predicate, normalize_key(self.object)


class GraphStore(ABC):
    @abstractmethod
    def ensure_schema(self) -> None: ...

    @abstractmethod
    def upsert_entities(self, entities: list[Entity]) -> None: ...

    @abstractmethod
    def upsert_relations(self, relations: list[Relation]) -> None: ...

    @abstractmethod
    def find_entities(self, terms: list[str], limit: int = 10) -> list[dict[str, Any]]:
        """Entity linking. Returns dicts with keys: key, name, label, score."""

    @abstractmethod
    def neighbourhood(
        self, keys: list[str], depth: int, limit: int, doc_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Facts around the given entities. Returns dicts matching schemas.query.GraphFact."""

    @abstractmethod
    def delete_by_doc(self, doc_id: str) -> None: ...

    @abstractmethod
    def get_metadata(self, top_n: int = 10) -> dict[str, Any]: ...

    @abstractmethod
    def subgraph(self, limit: int = 100, entity: str | None = None) -> list[dict[str, Any]]:
        """Edges for visualisation: s_key, s_name, s_label, type, confidence, o_key, o_name, o_label."""

    @abstractmethod
    def health(self) -> bool: ...

    def close(self) -> None:  # pragma: no cover - optional
        pass
