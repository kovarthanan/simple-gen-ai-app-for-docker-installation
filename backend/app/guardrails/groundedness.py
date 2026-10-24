"""Groundedness (faithfulness) scoring: how much of the answer is supported by the retrieved context.

Each answer sentence is compared to every context item using embedding similarity and
lexical overlap; a sentence is "supported" if either passes its threshold.
score = supported sentences / checked sentences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.ingestion.embedder import Embedder, cosine_similarity

logger = get_logger(__name__)

_CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9]+")
_ABSTAIN = re.compile(
    r"\b(i (?:do not|don't|cannot|can't) (?:know|find|answer|determine)"
    r"|not (?:enough|sufficient) information"
    r"|(?:no|not any) relevant (?:information|context|documents?)"
    r"|(?:context|documents?) (?:does|do) not (?:contain|mention|say|provide)"
    r"|couldn't find|could not find)",
    re.IGNORECASE,
)
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "was", "were",
    "be", "been", "it", "its", "this", "that", "these", "those", "as", "at", "by", "from", "has", "have",
    "had", "which", "who", "also", "their", "they", "there", "can", "will", "would", "based", "according",
}


def is_abstention(text: str) -> bool:
    return bool(_ABSTAIN.search(text))


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1}


@dataclass
class GroundednessResult:
    score: float
    supported: int
    total: int
    unsupported: list[str] = field(default_factory=list)
    method: str = "lexical"
    abstained: bool = False


class GroundednessScorer:
    def __init__(self, embedder: Embedder | None = None, sentence_threshold: float = 0.5,
                 lexical_threshold: float = 0.6):
        self.embedder = embedder
        self.sentence_threshold = sentence_threshold
        self.lexical_threshold = lexical_threshold

    def score(self, answer: str, contexts: list[str]) -> GroundednessResult:
        if is_abstention(answer):
            return GroundednessResult(1.0, 0, 0, method="abstention", abstained=True)
        clean = _CITATION.sub("", answer)
        sentences = [
            s.strip(" -*•\t") for s in _SENTENCE_SPLIT.split(clean)
            if len(_content_tokens(s)) >= 3
        ]
        if not sentences:
            return GroundednessResult(1.0, 0, 0, method="trivial")
        if not contexts:
            return GroundednessResult(0.0, 0, len(sentences), unsupported=sentences)

        context_tokens = [_content_tokens(c) for c in contexts]
        lexical = []
        for s in sentences:
            tokens = _content_tokens(s)
            lexical.append(max(len(tokens & ct) / len(tokens) for ct in context_tokens))

        semantic: list[float] | None = None
        method = "lexical"
        if self.embedder is not None:
            try:
                vectors = self.embedder.embed(sentences + contexts)
                sent_vecs, ctx_vecs = vectors[: len(sentences)], vectors[len(sentences):]
                semantic = [max(cosine_similarity(sv, cv) for cv in ctx_vecs) for sv in sent_vecs]
                method = "embedding+lexical"
            except Exception as exc:
                logger.warning("Embedding groundedness failed, using lexical only: %s", exc)

        supported, unsupported = 0, []
        for i, sentence in enumerate(sentences):
            ok = lexical[i] >= self.lexical_threshold or (
                semantic is not None and semantic[i] >= self.sentence_threshold
            )
            if ok:
                supported += 1
            else:
                unsupported.append(sentence)
        return GroundednessResult(round(supported / len(sentences), 3), supported, len(sentences),
                                  unsupported, method)
