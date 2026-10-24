"""Graph retrieval: link entities in the question, then expand their n-hop neighbourhood."""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.graph.base import GraphStore
from app.ingestion.entity_extractor import EntityExtractor
from app.schemas.query import GraphFact

logger = get_logger(__name__)

_STOPWORDS = {
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "does", "did", "do",
    "is", "are", "was", "were", "the", "and", "for", "with", "about", "from", "into", "that",
    "this", "these", "those", "there", "their", "have", "has", "had", "can", "could", "would",
    "should", "will", "tell", "explain", "describe", "list", "give", "show", "between", "relation",
    "relationship", "related", "please", "some", "any", "all", "more", "most", "other",
}
_CAPITALISED = re.compile(r"\b[A-Z][\w&.-]*(?:\s+(?:(?:of|the|&)\s+)?[A-Z][\w&.-]*)*")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")


def keyword_terms(query: str, max_terms: int = 6) -> list[str]:
    """Fallback entity linking without an LLM: capitalised phrases, then content words."""
    terms: list[str] = []
    for match in _CAPITALISED.finditer(query):
        phrase = match.group(0).strip(" .")
        if phrase and phrase.lower() not in _STOPWORDS:
            terms.append(phrase)
    for word in _WORD.findall(query):
        if word.lower() not in _STOPWORDS:
            terms.append(word)
    seen: set[str] = set()
    unique = []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    return unique[:max_terms]


class GraphRetriever:
    def __init__(self, store: GraphStore, extractor: EntityExtractor | None = None, max_terms: int = 6):
        self.store = store
        self.extractor = extractor
        self.max_terms = max_terms

    def link_entities(self, query: str) -> list[str]:
        terms: list[str] = []
        if self.extractor is not None:
            try:
                terms = self.extractor.extract_query_entities(query)
            except Exception as exc:
                logger.warning("LLM entity linking failed, using keyword fallback: %s", exc)
        if not terms:
            terms = keyword_terms(query, self.max_terms)
        return terms[: self.max_terms]

    def retrieve(
        self, query: str, depth: int, limit: int, doc_ids: list[str] | None = None
    ) -> tuple[list[str], list[GraphFact]]:
        terms = self.link_entities(query)
        if not terms:
            return [], []
        matches = self.store.find_entities(terms, limit=10)
        if not matches:
            return [], []
        keys = [m["key"] for m in matches]
        rows = self.store.neighbourhood(keys, depth=depth, limit=limit, doc_ids=doc_ids)
        facts = [GraphFact(**row) for row in rows]
        return [m["name"] for m in matches], facts
