"""Neo4j implementation of the GraphStore interface.

Model:
  (:Entity:<Label> {key, name, confidence, doc_ids, verified})
  (:Entity)-[:<PREDICATE> {confidence, doc_ids, chunk_ids, verified}]->(:Entity)
  (:Entity)-[:MENTIONED_IN]->(:Chunk {id, doc_id})   # chunk id == Qdrant point id
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from app.core.logging import get_logger
from app.graph import cypher_queries as Q
from app.graph.base import Entity, GraphStore, Relation, normalize_key, safe_label, safe_rel_type

logger = get_logger(__name__)

_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def _lucene_escape(term: str) -> str:
    term = _LUCENE_SPECIAL.sub(r"\\\1", term)
    # AND/OR/NOT are operators in Lucene; lower-case them so they're treated as words
    return re.sub(r"\b(AND|OR|NOT)\b", lambda m: m.group(1).lower(), term)


class Neo4jGraphStore(GraphStore):
    def __init__(self, uri: str, user: str, password: str, database: str | None = None):
        self._driver = GraphDatabase.driver(
            uri, auth=(user, password), connection_timeout=5.0, connection_acquisition_timeout=10.0,
            max_transaction_retry_time=5.0,  # fail fast when Neo4j is down instead of retrying for 30s
        )
        self._database = database
        self._schema_ready = False
        self._down_until = 0.0  # circuit breaker: skip calls for a while after Neo4j is found unreachable
        self._last_ok = 0.0

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        now = time.monotonic()
        if now < self._down_until:
            raise ServiceUnavailable("Neo4j was unreachable a moment ago; skipping graph call")
        try:
            if now - self._last_ok > 30:
                # quick connectivity check: fails in milliseconds, unlike execute_query's retry loop
                self._driver.verify_connectivity()
            records, _, _ = self._driver.execute_query(query, parameters_=params, database_=self._database)
        except (ServiceUnavailable, SessionExpired):
            self._down_until = time.monotonic() + 30  # don't make every request wait on retries
            raise
        self._down_until = 0.0
        self._last_ok = time.monotonic()
        return [r.data() for r in records]

    def _scalar(self, query: str, **params: Any) -> Any:
        rows = self._run(query, **params)
        return next(iter(rows[0].values())) if rows else None

    # -- schema --------------------------------------------------------------
    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for stmt in Q.SCHEMA_STATEMENTS:
            self._run(stmt)
        self._schema_ready = True

    # -- writes ----------------------------------------------------------------
    def upsert_entities(self, entities: list[Entity]) -> None:
        if not entities:
            return
        self.ensure_schema()
        by_label: dict[str, list[dict]] = defaultdict(list)
        for ent in entities:
            doc_id = ent.doc_ids[0] if ent.doc_ids else None
            by_label[safe_label(ent.label)].append(
                {
                    "key": ent.key,
                    "name": ent.name.strip(),
                    "confidence": float(ent.confidence),
                    "doc_ids": list(ent.doc_ids),
                    "verified": bool(ent.verified),
                    "chunks": [{"id": cid, "doc_id": doc_id} for cid in ent.chunk_ids],
                }
            )
        for label, rows in by_label.items():
            self._run(Q.UPSERT_ENTITIES.replace("__LABEL__", label), rows=rows)

    def upsert_relations(self, relations: list[Relation]) -> None:
        if not relations:
            return
        self.ensure_schema()
        by_type: dict[str, list[dict]] = defaultdict(list)
        for rel in relations:
            by_type[safe_rel_type(rel.predicate)].append(
                {
                    "s_key": normalize_key(rel.subject),
                    "s_name": rel.subject.strip(),
                    "o_key": normalize_key(rel.object),
                    "o_name": rel.object.strip(),
                    "confidence": float(rel.confidence),
                    "doc_id": rel.doc_id,
                    "chunk_ids": list(rel.chunk_ids),
                    "verified": bool(rel.verified),
                }
            )
        for rel_type, rows in by_type.items():
            self._run(Q.UPSERT_RELATIONS.replace("__PRED__", rel_type), rows=rows)

    # -- retrieval -------------------------------------------------------------
    def find_entities(self, terms: list[str], limit: int = 10) -> list[dict[str, Any]]:
        terms = [t for t in (t.strip() for t in terms) if t]
        if not terms:
            return []
        found: dict[str, dict[str, Any]] = {}
        for row in self._run(Q.FIND_ENTITIES_EXACT, keys=[normalize_key(t) for t in terms]):
            found[row["key"]] = row
        for term in terms:
            escaped = _lucene_escape(term)
            words = escaped.split()
            # phrase match OR fuzzy match on each word
            lucene = f'"{escaped}" OR ' + " ".join(f"{w}~1" if len(w) > 3 else w for w in words)
            try:
                rows = self._run(Q.FIND_ENTITIES_FULLTEXT, q=lucene, limit=limit)
            except Exception as exc:  # malformed query or index missing
                logger.debug("Fulltext lookup failed for %r: %s", term, exc)
                continue
            for row in rows:
                if row["key"] not in found or row["score"] > found[row["key"]]["score"]:
                    found[row["key"]] = row
        return sorted(found.values(), key=lambda r: r["score"], reverse=True)[:limit]

    def neighbourhood(
        self, keys: list[str], depth: int, limit: int, doc_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        if not keys:
            return []
        depth = max(1, min(int(depth), 3))
        query = Q.NEIGHBOURHOOD.replace("__DEPTH__", str(depth))
        return self._run(query, keys=keys, per_entity=max(limit, 10), limit=limit, doc_ids=doc_ids or None)

    # -- deletes ---------------------------------------------------------------
    def delete_by_doc(self, doc_id: str) -> None:
        self._run(Q.DELETE_DOC_RELATIONS, doc_id=doc_id)
        self._run(Q.DELETE_DOC_CHUNKS, doc_id=doc_id)
        self._run(Q.DELETE_DOC_ENTITIES, doc_id=doc_id)

    # -- metadata --------------------------------------------------------------
    def get_metadata(self, top_n: int = 10) -> dict[str, Any]:
        return {
            "total_nodes": self._scalar(Q.COUNT_ENTITIES) or 0,
            "total_relationships": self._scalar(Q.COUNT_RELATIONSHIPS) or 0,
            "total_chunks_linked": self._scalar(Q.COUNT_CHUNKS) or 0,
            "verified_entities": self._scalar(Q.COUNT_VERIFIED) or 0,
            "isolated_nodes": self._scalar(Q.COUNT_ISOLATED) or 0,
            "node_labels": self._run(Q.NODE_COUNTS_BY_LABEL),
            "relationship_types": self._run(Q.REL_COUNTS_BY_TYPE),
            "top_entities": self._run(Q.TOP_ENTITIES_BY_DEGREE, limit=top_n),
            "property_keys": sorted(self._scalar(Q.PROPERTY_KEYS) or []),
        }

    def subgraph(self, limit: int = 100, entity: str | None = None) -> list[dict[str, Any]]:
        key = normalize_key(entity) if entity else None
        return self._run(Q.SUBGRAPH, key=key, limit=limit)

    def health(self) -> bool:
        self._driver.verify_connectivity()
        self._down_until = 0.0  # reachable again: close the circuit breaker
        return True

    def close(self) -> None:
        self._driver.close()
