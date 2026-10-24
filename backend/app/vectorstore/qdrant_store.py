"""Qdrant implementation of the VectorStore interface."""
from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient, models

from app.core.exceptions import StoreError
from app.core.logging import get_logger
from app.vectorstore.base import VectorRecord, VectorSearchResult, VectorStore

logger = get_logger(__name__)

_INDEXED_PAYLOAD_FIELDS = ("doc_id", "source")


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


class QdrantVectorStore(VectorStore):
    def __init__(self, url: str, api_key: str | None, collection: str, timeout: int = 10):
        self.client = QdrantClient(url=url, api_key=api_key, timeout=timeout)
        self.collection = collection
        self._ready = False

    # -- setup -------------------------------------------------------------
    def _exists(self) -> bool:
        return self.client.collection_exists(self.collection)

    def ensure_collection(self, dimension: int) -> None:
        if self._ready:
            return
        if not self._exists():
            logger.info("Creating Qdrant collection '%s' (dim=%d)", self.collection, dimension)
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
            )
            for field_name in _INDEXED_PAYLOAD_FIELDS:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
        else:
            existing = self._dimension()
            if existing is not None and existing != dimension:
                raise StoreError(
                    f"Collection '{self.collection}' has dimension {existing} but the embedding "
                    f"model produces {dimension}. Use a new QDRANT_COLLECTION or re-index."
                )
        self._ready = True

    def _dimension(self) -> int | None:
        params = self.client.get_collection(self.collection).config.params.vectors
        if isinstance(params, dict):  # named vectors
            params = next(iter(params.values()), None)
        return getattr(params, "size", None)

    # -- data ------------------------------------------------------------------
    def upsert(self, records: list[VectorRecord], batch_size: int = 128) -> None:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            self.client.upsert(
                collection_name=self.collection,
                points=[models.PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in batch],
                wait=True,
            )

    def search(
        self, vector: list[float], top_k: int, doc_ids: list[str] | None = None
    ) -> list[VectorSearchResult]:
        if not self._ready and not self._exists():
            return []  # nothing ingested yet
        query_filter = None
        if doc_ids:
            query_filter = models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids))]
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            VectorSearchResult(id=str(p.id), score=float(p.score), payload=p.payload or {})
            for p in response.points
        ]

    def delete_by_doc(self, doc_id: str) -> None:
        if not self._exists():
            return
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
                )
            ),
            wait=True,
        )

    # -- metadata ----------------------------------------------------------
    def get_metadata(self) -> dict[str, Any]:
        if not self._exists():
            return {"exists": False, "vectors_count": 0}
        info = self.client.get_collection(self.collection)
        params = info.config.params.vectors
        if isinstance(params, dict):
            params = next(iter(params.values()), None)
        return {
            "exists": True,
            "vectors_count": self.client.count(self.collection, exact=True).count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "dimension": getattr(params, "size", None),
            "distance": str(_enum_value(getattr(params, "distance", None))),
            "status": str(_enum_value(info.status)),
            "segments_count": info.segments_count,
            "payload_fields": sorted((info.payload_schema or {}).keys()),
        }

    def health(self) -> bool:
        self.client.get_collections()
        return True

    def close(self) -> None:
        self.client.close()
