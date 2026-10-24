"""The question-answering flow:

input guardrails -> hybrid retrieval (Qdrant + Neo4j in parallel) -> fusion -> LLM
-> output guardrails -> confidence -> answer, or hold for human review
"""
from __future__ import annotations

import asyncio
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models import QueryLog
from app.guardrails.runner import GuardrailRunner
from app.hitl import review_queue
from app.hitl.notifications import Notifier
from app.hitl.policies import HITLPolicy
from app.guardrails.output_guard import parse_citations
from app.llm.client import LLMClient
from app.llm.prompts import RAG_SYSTEM_PROMPT, build_rag_prompt
from app.retrieval.hybrid_retriever import HybridResult, HybridRetriever
from app.schemas.query import ContextItem, GuardFlag, QueryRequest, QueryResponse
from app.services.audit_service import log_event

logger = get_logger(__name__)

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in the indexed documents or the knowledge graph to answer this question."
)


def compute_confidence(groundedness: float | None, contexts: list[ContextItem], citations: list[int]) -> float:
    """Blend of answer groundedness, retrieval strength and citation presence (0-1)."""
    g = groundedness if groundedness is not None else 0.5
    vector_scores = [c.source_score for c in contexts if c.origin == "vector"]
    retrieval = max(vector_scores) if vector_scores else (0.5 if contexts else 0.0)
    retrieval = max(0.0, min(1.0, retrieval))
    cite = 1.0 if citations else 0.5
    return round(0.6 * g + 0.25 * retrieval + 0.15 * cite, 3)


class RAGService:
    def __init__(self, settings: Settings, retriever: HybridRetriever, llm: LLMClient,
                 guardrails: GuardrailRunner, hitl_policy: HITLPolicy, notifier: Notifier):
        self.settings = settings
        self.retriever = retriever
        self.llm = llm
        self.guardrails = guardrails
        self.hitl = hitl_policy
        self.notifier = notifier

    async def answer(self, db: Session, req: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        query_id = str(uuid.uuid4())
        latency: dict[str, float] = {}
        log = QueryLog(id=query_id, query=req.query, user=req.user, status="answered")

        # 1. Input guardrails
        t = time.perf_counter()
        in_report = self.guardrails.run_input(req.query)
        latency["input_guard"] = _ms(t)
        flags: list[GuardFlag] = in_report.flags()
        if in_report.blocked:
            log.status = "blocked"
            log.message = f"Blocked by input guardrails: {in_report.block_reason}"
            return self._finish(db, log, flags, latency, started, event="query.blocked")
        query = in_report.text
        log.sanitized_query = query if query != req.query else None

        # 2. Hybrid retrieval
        s = self.settings
        retrieval: HybridResult = await self.retriever.retrieve(
            query,
            top_k=req.top_k or s.vector_top_k,
            graph_depth=req.graph_depth or s.graph_depth,
            graph_limit=req.graph_limit or s.graph_limit,
            final_top_k=req.final_top_k or s.final_top_k,
            use_vector=req.use_vector,
            use_graph=req.use_graph,
            doc_ids=req.doc_ids,
        )
        latency.update(retrieval.latency_ms)
        log.matched_entities = retrieval.matched_entities
        if not retrieval.contexts:
            log.answer = NO_CONTEXT_ANSWER
            log.confidence = 0.0
            if retrieval.errors:
                log.message = "Retrieval problems: " + "; ".join(f"{k}: {v}" for k, v in retrieval.errors.items())
            return self._finish(db, log, flags, latency, started)

        # 3. Generate
        prompt, numbered = build_rag_prompt(query, retrieval.contexts)
        t = time.perf_counter()
        llm_response = await asyncio.to_thread(self.llm.complete, prompt, RAG_SYSTEM_PROMPT)
        latency["llm"] = _ms(t)
        draft = llm_response.text.strip()

        # 4. Output guardrails
        t = time.perf_counter()
        out_report = self.guardrails.run_output(draft, [c.content for c in numbered])
        latency["output_guard"] = _ms(t)
        flags += out_report.flags()
        answer = out_report.text
        citations = parse_citations(answer, len(numbered))
        for item in numbered:
            item.cited = item.citation in citations
        log.contexts = [c.model_dump() for c in numbered]
        log.citations = citations
        log.groundedness = out_report.score_of("groundedness")
        log.draft_answer = answer
        if out_report.blocked:
            log.status = "blocked"
            log.message = f"Answer blocked by output guardrails: {out_report.block_reason}"
            return self._finish(db, log, flags, latency, started, event="query.blocked")

        log.confidence = compute_confidence(log.groundedness, numbered, citations)
        notes = []
        if retrieval.errors:
            notes.append("Partial retrieval: " + "; ".join(f"{k} failed" for k in retrieval.errors))

        # 5. Human-in-the-loop routing
        decision = self.hitl.review_answer(log.confidence, out_report)
        if decision.needs_review:
            item = review_queue.enqueue(
                db, "answer",
                payload={"query": query, "draft_answer": answer, "contexts": log.contexts,
                         "guard_flags": [f.model_dump() for f in flags], "confidence": log.confidence},
                reason="; ".join(decision.reasons), confidence=log.confidence, reference_id=query_id,
            )
            log.review_id = item.id
            log.status = "pending_review"
            if self.hitl.hold_answers:
                log.answer = None
                notes.insert(0, "This answer needs human review before it is shown. Check back using the query id.")
            else:
                log.answer = answer
                notes.insert(0, "Unverified: this answer is waiting for human review.")
            self.notifier.notify(f"Answer for query {query_id} needs review ({'; '.join(decision.reasons)})")
        else:
            log.answer = answer
        log.message = " ".join(notes) or None
        return self._finish(db, log, flags, latency, started,
                            event="query.pending_review" if decision.needs_review else "query.answered")

    def _finish(self, db: Session, log: QueryLog, flags: list[GuardFlag], latency: dict[str, float],
                started: float, event: str = "query.answered") -> QueryResponse:
        latency["total"] = _ms(started)
        log.guard_flags = [f.model_dump() for f in flags]
        log.latency_ms = latency
        db.add(log)
        log_event(db, event, log.user or "user", query_id=log.id, status=log.status, confidence=log.confidence,
                  flagged=[f.guard for f in flags if not f.passed])
        db.commit()
        return to_response(log)

    # -- reads -------------------------------------------------------------------------
    @staticmethod
    def get_result(db: Session, query_id: str) -> QueryResponse:
        log = db.get(QueryLog, query_id)
        if log is None:
            raise NotFoundError(f"Query {query_id} not found")
        return to_response(log)

    @staticmethod
    def history(db: Session, limit: int = 50, status: str | None = None) -> list[QueryLog]:
        stmt = select(QueryLog)
        if status:
            stmt = stmt.where(QueryLog.status == status)
        return list(db.scalars(stmt.order_by(QueryLog.created_at.desc()).limit(limit)).all())


def to_response(log: QueryLog) -> QueryResponse:
    return QueryResponse(
        query_id=log.id, status=log.status, answer=log.answer, message=log.message,
        confidence=log.confidence, groundedness=log.groundedness, citations=log.citations or [],
        contexts=log.contexts or [], matched_entities=log.matched_entities or [],
        guard_flags=log.guard_flags or [], latency_ms=log.latency_ms or {},
        review_id=log.review_id, reviewed=bool(log.reviewed), created_at=log.created_at,
    )


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
