"""Run vector and graph retrieval in parallel, then fuse them into one ranked context list."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.logging import get_logger
from app.retrieval.graph_retriever import GraphRetriever
from app.retrieval.reranker import Reranker
from app.retrieval.vector_retriever import VectorRetriever
from app.schemas.query import ContextItem, GraphFact, VectorHit

logger = get_logger(__name__)


@dataclass
class HybridResult:
    contexts: list[ContextItem] = field(default_factory=list)
    vector_hits: list[VectorHit] = field(default_factory=list)
    graph_facts: list[GraphFact] = field(default_factory=list)
    matched_entities: list[str] = field(default_factory=list)
    latency_ms: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def _vector_items(hits: list[VectorHit]) -> list[ContextItem]:
    return [
        ContextItem(
            id=f"vec:{h.chunk_id}",
            origin="vector",
            content=h.text,
            source_rank=i,
            source_score=round(h.score, 4),
            metadata={"chunk_id": h.chunk_id, "doc_id": h.doc_id, "source": h.source,
                      "page": h.page, "chunk_index": h.chunk_index},
        )
        for i, h in enumerate(hits, start=1)
    ]


def _graph_items(facts: list[GraphFact]) -> list[ContextItem]:
    return [
        ContextItem(
            id=f"kg:{f.subject}|{f.predicate}|{f.object}".lower(),
            origin="graph",
            content=f.as_text(),
            source_rank=i,
            source_score=round(f.confidence, 4),
            metadata={"subject": f.subject, "subject_label": f.subject_label, "predicate": f.predicate,
                      "object": f.object, "object_label": f.object_label, "hops": f.hops, "doc_ids": f.doc_ids},
        )
        for i, f in enumerate(facts, start=1)
    ]


class HybridRetriever:
    def __init__(self, vector: VectorRetriever, graph: GraphRetriever, reranker: Reranker):
        self.vector = vector
        self.graph = graph
        self.reranker = reranker

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        graph_depth: int,
        graph_limit: int,
        final_top_k: int,
        use_vector: bool = True,
        use_graph: bool = True,
        doc_ids: list[str] | None = None,
    ) -> HybridResult:
        result = HybridResult()

        async def timed(name: str, fn: Callable[..., Any], *args: Any) -> Any:
            start = time.perf_counter()
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as exc:  # one store failing shouldn't kill the whole answer
                logger.exception("%s retrieval failed", name)
                result.errors[name] = f"{type(exc).__name__}: {exc}"
                return None
            finally:
                result.latency_ms[f"{name}_retrieval"] = round((time.perf_counter() - start) * 1000, 1)

        tasks = []
        if use_vector:
            tasks.append(timed("vector", self.vector.retrieve, query, top_k, doc_ids))
        if use_graph:
            tasks.append(timed("graph", self.graph.retrieve, query, graph_depth, graph_limit, doc_ids))
        outputs = await asyncio.gather(*tasks)

        idx = 0
        if use_vector:
            result.vector_hits = outputs[idx] or []
            idx += 1
        if use_graph and outputs[idx]:
            result.matched_entities, result.graph_facts = outputs[idx]

        start = time.perf_counter()
        result.contexts = self.reranker.rerank(
            query,
            {"vector": _vector_items(result.vector_hits), "graph": _graph_items(result.graph_facts)},
            top_n=final_top_k,
        )
        result.latency_ms["fusion"] = round((time.perf_counter() - start) * 1000, 1)
        return result
