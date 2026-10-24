"""Semantic top-k search over the vector store."""
from __future__ import annotations

from app.ingestion.embedder import Embedder
from app.schemas.query import VectorHit
from app.vectorstore.base import VectorStore

_CORE_FIELDS = {"chunk_id", "doc_id", "text", "source", "page", "chunk_index"}


class VectorRetriever:
    def __init__(self, embedder: Embedder, store: VectorStore):
        self.embedder = embedder
        self.store = store

    def retrieve(self, query: str, top_k: int, doc_ids: list[str] | None = None) -> list[VectorHit]:
        vector = self.embedder.embed_query(query)
        hits: list[VectorHit] = []
        for result in self.store.search(vector, top_k=top_k, doc_ids=doc_ids):
            p = result.payload
            hits.append(
                VectorHit(
                    chunk_id=str(p.get("chunk_id", result.id)),
                    doc_id=str(p.get("doc_id", "")),
                    text=str(p.get("text", "")),
                    score=result.score,
                    source=p.get("source"),
                    page=p.get("page"),
                    chunk_index=p.get("chunk_index"),
                    metadata={k: v for k, v in p.items() if k not in _CORE_FIELDS},
                )
            )
        return hits
