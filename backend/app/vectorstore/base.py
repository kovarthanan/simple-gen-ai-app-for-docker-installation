"""Vector store interface. Implement this to swap Qdrant for Chroma, pgvector, etc."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorSearchResult:
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    collection: str

    @abstractmethod
    def ensure_collection(self, dimension: int) -> None:
        """Create the collection if it doesn't exist (idempotent)."""

    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    def search(
        self, vector: list[float], top_k: int, doc_ids: list[str] | None = None
    ) -> list[VectorSearchResult]: ...

    @abstractmethod
    def delete_by_doc(self, doc_id: str) -> None: ...

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Keys: exists, vectors_count, indexed_vectors_count, dimension, distance,
        status, segments_count, payload_fields."""

    @abstractmethod
    def health(self) -> bool: ...

    def close(self) -> None:  # pragma: no cover - optional
        pass
