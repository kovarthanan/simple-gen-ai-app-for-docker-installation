"""Test fixtures: in-memory fakes for the embedder, both stores and the LLM, so the suite
runs without Docker, model downloads or API keys."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import build_container
from app.config import Settings
from app.graph.base import Entity, GraphStore, Relation, normalize_key, safe_label, safe_rel_type
from app.ingestion.embedder import Embedder, cosine_similarity
from app.llm.client import LLMClient, LLMResponse
from app.llm.prompts import QUERY_ENTITY_SYSTEM, RAG_SYSTEM_PROMPT
from app.main import create_app
from app.vectorstore.base import VectorRecord, VectorSearchResult, VectorStore

REVIEWER = {"X-API-Key": "test-key", "X-Reviewer": "alice-reviewer"}


class FakeEmbedder(Embedder):
    """Hashed bag-of-words vectors: deterministic and similar for overlapping text."""

    model_name = "fake-hash-embedder"

    @property
    def dimension(self) -> int:
        return 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dimension
            for tok in re.findall(r"[a-z0-9]+", text.lower()):
                vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dimension] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class InMemoryVectorStore(VectorStore):
    collection = "test"

    def __init__(self):
        self.records: dict[str, VectorRecord] = {}
        self.dim: int | None = None

    def ensure_collection(self, dimension):
        self.dim = dimension

    def upsert(self, records):
        for r in records:
            self.records[r.id] = r

    def search(self, vector, top_k, doc_ids=None):
        scored = [
            VectorSearchResult(r.id, cosine_similarity(vector, r.vector), r.payload)
            for r in self.records.values()
            if not doc_ids or r.payload.get("doc_id") in doc_ids
        ]
        return sorted(scored, key=lambda s: s.score, reverse=True)[:top_k]

    def delete_by_doc(self, doc_id):
        self.records = {k: v for k, v in self.records.items() if v.payload.get("doc_id") != doc_id}

    def get_metadata(self):
        return {"exists": bool(self.records), "vectors_count": len(self.records), "dimension": self.dim,
                "distance": "Cosine", "status": "green", "payload_fields": ["doc_id", "source"]}

    def health(self):
        return True


class InMemoryGraphStore(GraphStore):
    def __init__(self):
        self.entities: dict[str, dict[str, Any]] = {}
        self.relations: dict[tuple[str, str, str], dict[str, Any]] = {}

    def ensure_schema(self):
        pass

    def upsert_entities(self, entities: list[Entity]):
        for e in entities:
            cur = self.entities.setdefault(e.key, {"name": e.name, "label": safe_label(e.label), "confidence": 0,
                                                    "doc_ids": [], "verified": False})
            cur["label"] = safe_label(e.label)
            cur["confidence"] = max(cur["confidence"], e.confidence)
            cur["doc_ids"] = sorted(set(cur["doc_ids"]) | set(e.doc_ids))
            cur["verified"] = cur["verified"] or e.verified

    def upsert_relations(self, relations: list[Relation]):
        for r in relations:
            for name in (r.subject, r.object):
                self.entities.setdefault(normalize_key(name), {"name": name, "label": "Other", "confidence": r.confidence,
                                                                "doc_ids": [], "verified": False})
            key = (normalize_key(r.subject), safe_rel_type(r.predicate), normalize_key(r.object))
            cur = self.relations.setdefault(key, {"confidence": 0, "doc_ids": [], "verified": False})
            cur["confidence"] = max(cur["confidence"], r.confidence)
            if r.doc_id:
                cur["doc_ids"] = sorted(set(cur["doc_ids"]) | {r.doc_id})
            cur["verified"] = cur["verified"] or r.verified

    def find_entities(self, terms, limit=10):
        out = []
        for key, e in self.entities.items():
            for t in terms:
                if normalize_key(t) == key or normalize_key(t) in key:
                    out.append({"key": key, "name": e["name"], "label": e["label"], "score": 1.0})
                    break
        return out[:limit]

    def neighbourhood(self, keys, depth, limit, doc_ids=None):
        adjacency = defaultdict(list)
        for (s, p, o), data in self.relations.items():
            adjacency[s].append((s, p, o))
            adjacency[o].append((s, p, o))
        seen, facts, frontier = set(), [], set(keys)
        for hop in range(1, depth + 1):
            nxt = set()
            for node in frontier:
                for edge in adjacency[node]:
                    if edge in seen:
                        continue
                    seen.add(edge)
                    s, p, o = edge
                    data = self.relations[edge]
                    if doc_ids and not set(data["doc_ids"]) & set(doc_ids):
                        continue
                    facts.append({"subject": self.entities[s]["name"], "subject_label": self.entities[s]["label"],
                                  "predicate": p, "object": self.entities[o]["name"],
                                  "object_label": self.entities[o]["label"], "confidence": data["confidence"],
                                  "doc_ids": data["doc_ids"], "hops": hop})
                    nxt.update({s, o})
            frontier = nxt
        return facts[:limit]

    def delete_by_doc(self, doc_id):
        for key in list(self.relations):
            ids = [d for d in self.relations[key]["doc_ids"] if d != doc_id]
            if ids:
                self.relations[key]["doc_ids"] = ids
            else:
                del self.relations[key]
        for key in list(self.entities):
            ids = [d for d in self.entities[key]["doc_ids"] if d != doc_id]
            self.entities[key]["doc_ids"] = ids
            linked = any(key in (s, o) for s, _, o in self.relations)
            if not ids and not linked:
                del self.entities[key]

    def get_metadata(self, top_n=10):
        labels, types, degree = defaultdict(int), defaultdict(int), defaultdict(int)
        for e in self.entities.values():
            labels[e["label"]] += 1
        for s, p, o in self.relations:
            types[p] += 1
            degree[s] += 1
            degree[o] += 1
        top = sorted(self.entities, key=lambda k: degree[k], reverse=True)[:top_n]
        return {
            "total_nodes": len(self.entities), "total_relationships": len(self.relations),
            "verified_entities": sum(1 for e in self.entities.values() if e["verified"]),
            "isolated_nodes": sum(1 for k in self.entities if degree[k] == 0),
            "node_labels": [{"label": k, "count": v} for k, v in labels.items()],
            "relationship_types": [{"type": k, "count": v} for k, v in types.items()],
            "top_entities": [{"entity": self.entities[k]["name"], "label": self.entities[k]["label"],
                              "degree": degree[k]} for k in top],
            "property_keys": ["name", "key", "confidence", "doc_ids"],
        }

    def subgraph(self, limit=100, entity=None):
        rows = []
        for (s, p, o), data in self.relations.items():
            if entity and normalize_key(entity) not in (s, o):
                continue
            rows.append({"s_key": s, "s_name": self.entities[s]["name"], "s_label": self.entities[s]["label"],
                         "type": p, "confidence": data["confidence"],
                         "o_key": o, "o_name": self.entities[o]["name"], "o_label": self.entities[o]["label"]})
        return rows[:limit]

    def health(self):
        return True


DEFAULT_EXTRACTION = {
    "entities": [
        {"name": "Alice", "type": "Person", "confidence": 0.95},
        {"name": "Acme Corp", "type": "Organization", "confidence": 0.92},
        {"name": "Chennai", "type": "Location", "confidence": 0.55},   # -> review queue
        {"name": "Blob", "type": "Other", "confidence": 0.1},          # -> dropped
    ],
    "relations": [
        {"subject": "Alice", "predicate": "works at", "object": "Acme Corp", "confidence": 0.9},      # auto
        {"subject": "Acme Corp", "predicate": "LOCATED_IN", "object": "Chennai", "confidence": 0.85},  # review
    ],
}


class FakeLLM(LLMClient):
    model = "fake-llm"

    def __init__(self):
        self.extraction = DEFAULT_EXTRACTION
        self.answer_override: str | None = None
        self.calls: list[tuple[str | None, str]] = []

    def complete(self, prompt, system=None, max_tokens=None, temperature=None):
        self.calls.append((system, prompt))
        if system == QUERY_ENTITY_SYSTEM:
            question = prompt.split("Question:", 1)[1]
            names = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*", question)
            return LLMResponse(json.dumps({"entities": names}), self.model)
        if system and system.startswith("You are a knowledge graph extraction system"):
            return LLMResponse(json.dumps(self.extraction), self.model)
        if system == RAG_SYSTEM_PROMPT:
            if self.answer_override is not None:
                return LLMResponse(self.answer_override, self.model)
            match = re.search(r"\[1\][^\n]*\n(.+?)(?:\n|$)", prompt)
            first = match.group(1).split(". ")[0].rstrip(".") if match else "No passage"
            return LLMResponse(f"{first}. [1]", self.model)
        return LLMResponse("{}", self.model)


@pytest.fixture
def fakes():
    return {"embedder": FakeEmbedder(), "vector_store": InMemoryVectorStore(),
            "graph_store": InMemoryGraphStore(), "llm": FakeLLM()}


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url="sqlite://", reviewer_api_key="test-key",
                    upload_dir=str(tmp_path / "uploads"), llm_provider="anthropic")


@pytest.fixture
def container(settings, fakes):
    return build_container(settings, **fakes)


@pytest.fixture
def client(container):
    with TestClient(create_app(container)) as c:
        yield c


SAMPLE_TEXT = (
    "Alice works at Acme Corp in Chennai. She leads the platform engineering team there. "
    "Acme Corp builds logistics software used by retailers across India. "
    "Contact Alice at alice@example.com for partnership questions."
)


@pytest.fixture
def ingested(client):
    r = client.post("/ingest/text", json={"text": SAMPLE_TEXT, "title": "acme.txt"})
    assert r.status_code == 200, r.text
    return r.json()
