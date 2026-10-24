"""Fuse vector and graph results with Reciprocal Rank Fusion, optionally rerank with a cross-encoder."""
from __future__ import annotations

import threading

from app.core.logging import get_logger
from app.schemas.query import ContextItem

logger = get_logger(__name__)


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[ContextItem]], k: int = 60, weights: dict[str, float] | None = None
) -> list[ContextItem]:
    """score(item) = sum over lists of weight / (k + rank). Items are de-duplicated by id."""
    weights = weights or {}
    scores: dict[str, float] = {}
    items: dict[str, ContextItem] = {}
    for name, ranked in ranked_lists.items():
        w = weights.get(name, 1.0)
        for rank, item in enumerate(ranked, start=1):
            scores[item.id] = scores.get(item.id, 0.0) + w / (k + rank)
            items.setdefault(item.id, item)
    fused = sorted(items.values(), key=lambda it: scores[it.id], reverse=True)
    for item in fused:
        item.score = round(scores[item.id], 6)
    return fused


class Reranker:
    def __init__(self, k: int = 60, weights: dict[str, float] | None = None,
                 cross_encoder_model: str | None = None):
        self.k = k
        self.weights = weights or {}
        self.cross_encoder_model = cross_encoder_model
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    self._model = CrossEncoder(self.cross_encoder_model)
        return self._model

    def rerank(self, query: str, ranked_lists: dict[str, list[ContextItem]], top_n: int) -> list[ContextItem]:
        fused = reciprocal_rank_fusion(ranked_lists, self.k, self.weights)
        if self.cross_encoder_model and fused:
            try:
                scores = self._load().predict([(query, item.content) for item in fused])
                for item, score in zip(fused, scores):
                    item.score = float(score)
                fused.sort(key=lambda it: it.score, reverse=True)
            except Exception as exc:
                logger.warning("Cross-encoder rerank failed, keeping RRF order: %s", exc)
        fused = fused[:top_n]
        for rank, item in enumerate(fused, start=1):
            item.rank = rank
        return fused
