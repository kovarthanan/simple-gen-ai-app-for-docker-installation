"""Combines vector DB, knowledge graph and app-DB statistics for the metadata dashboard."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.logging import get_logger
from app.db.models import Document, Feedback, QueryLog, ReviewItem
from app.graph.base import GraphStore
from app.schemas.metadata import (
    DocumentStat, GraphMetadata, Subgraph, SubgraphEdge, SubgraphNode, SummaryMetadata, VectorMetadata,
)
from app.vectorstore.base import VectorStore

logger = get_logger(__name__)


class MetadataService:
    def __init__(self, settings: Settings, vector_store: VectorStore, graph_store: GraphStore, embedding_model: str):
        self.settings = settings
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.embedding_model = embedding_model

    def vector(self, db: Session, doc_limit: int = 200) -> VectorMetadata:
        docs = db.scalars(select(Document).order_by(Document.created_at.desc()).limit(doc_limit)).all()
        doc_stats = [
            DocumentStat(doc_id=d.id, filename=d.filename, status=d.status, num_chunks=d.num_chunks,
                         num_entities=d.num_entities, num_relations=d.num_relations,
                         pending_review=d.pending_review, created_at=d.created_at)
            for d in docs
        ]
        base = {"collection": self.vector_store.collection, "embedding_model": self.embedding_model,
                "documents": doc_stats}
        try:
            return VectorMetadata(**base, **self.vector_store.get_metadata())
        except Exception as exc:
            logger.warning("Vector metadata unavailable: %s", exc)
            return VectorMetadata(**base, available=False, error=f"{type(exc).__name__}: {exc}")

    def graph(self, top_n: int = 10) -> GraphMetadata:
        try:
            return GraphMetadata(**self.graph_store.get_metadata(top_n=top_n))
        except Exception as exc:
            logger.warning("Graph metadata unavailable: %s", exc)
            return GraphMetadata(available=False, error=f"{type(exc).__name__}: {exc}")

    def summary(self, db: Session) -> SummaryMetadata:
        feedback = dict(db.execute(select(Feedback.rating, func.count()).group_by(Feedback.rating)).all())
        fb_total = feedback.get(1, 0) + feedback.get(-1, 0)
        reviews = dict(
            db.execute(
                select(ReviewItem.item_type, func.count())
                .where(ReviewItem.status == "pending").group_by(ReviewItem.item_type)
            ).all()
        )
        return SummaryMetadata(
            vector=self.vector(db, doc_limit=20),
            graph=self.graph(),
            documents_total=db.scalar(select(func.count(Document.id))) or 0,
            chunks_total=db.scalar(select(func.coalesce(func.sum(Document.num_chunks), 0))) or 0,
            queries_total=db.scalar(select(func.count(QueryLog.id))) or 0,
            queries_by_status=dict(db.execute(select(QueryLog.status, func.count()).group_by(QueryLog.status)).all()),
            pending_reviews=sum(reviews.values()),
            reviews_by_type=reviews,
            feedback_total=fb_total,
            positive_feedback_rate=round(feedback.get(1, 0) / fb_total, 3) if fb_total else None,
            last_ingested_at=db.scalar(select(func.max(Document.created_at))),
        )

    def subgraph(self, limit: int = 100, entity: str | None = None) -> Subgraph:
        rows = self.graph_store.subgraph(limit=limit, entity=entity)
        nodes: dict[str, SubgraphNode] = {}
        edges: list[SubgraphEdge] = []
        for r in rows:
            nodes.setdefault(r["s_key"], SubgraphNode(id=r["s_key"], name=r["s_name"], label=r.get("s_label")))
            nodes.setdefault(r["o_key"], SubgraphNode(id=r["o_key"], name=r["o_name"], label=r.get("o_label")))
            edges.append(SubgraphEdge(source=r["s_key"], target=r["o_key"], type=r["type"],
                                      confidence=r.get("confidence", 1.0)))
        return Subgraph(nodes=list(nodes.values()), edges=edges)
