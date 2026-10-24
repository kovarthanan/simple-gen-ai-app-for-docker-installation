"""Runs guard chains for each stage and aggregates the results into a GuardReport."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.guardrails.base import Guard, GuardAction, GuardResult
from app.guardrails.groundedness import GroundednessScorer
from app.guardrails.ingest_guard import build_ingest_content_guards, build_ingest_file_guards
from app.guardrails.input_guard import PIIGuard, build_input_guards
from app.guardrails.output_guard import build_output_guards
from app.ingestion.embedder import Embedder
from app.schemas.query import GuardFlag

logger = get_logger(__name__)


@dataclass
class GuardReport:
    stage: str
    original_text: str
    text: str  # possibly modified (e.g. redacted)
    results: list[GuardResult] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(r.action == GuardAction.BLOCK and not r.passed for r in self.results)

    @property
    def block_reason(self) -> str | None:
        for r in self.results:
            if r.action == GuardAction.BLOCK and not r.passed:
                return r.reason
        return None

    @property
    def flagged_guards(self) -> list[str]:
        return [r.guard for r in self.results if r.action == GuardAction.FLAG and not r.passed]

    @property
    def redacted(self) -> bool:
        return any(r.action == GuardAction.REDACT for r in self.results)

    def get(self, guard: str) -> GuardResult | None:
        return next((r for r in self.results if r.guard == guard), None)

    def score_of(self, guard: str) -> float | None:
        result = self.get(guard)
        return result.score if result else None

    def flags(self) -> list[GuardFlag]:
        return [
            GuardFlag(guard=r.guard, stage=self.stage, passed=r.passed, action=r.action.value,
                      reason=r.reason, score=r.score)
            for r in self.results
        ]


class GuardrailRunner:
    def __init__(self, policy: dict[str, Any], embedder: Embedder | None = None):
        self.policy = policy
        use_presidio = bool(policy.get("use_presidio", False))
        out_cfg = policy["output"]
        scorer = GroundednessScorer(embedder, out_cfg.get("groundedness", {}).get("sentence_threshold", 0.5))
        self.input_guards = build_input_guards(policy["input"], use_presidio)
        self.output_guards = build_output_guards(out_cfg, scorer, use_presidio)
        self.ingest_file_guards = build_ingest_file_guards(policy["ingest"])
        self.ingest_content_guards = build_ingest_content_guards(policy["ingest"])
        doc_pii = policy["ingest"].get("pii", {})
        self._doc_pii = (
            PIIGuard(doc_pii.get("action", "redact"), doc_pii.get("entities"), use_presidio, name="document_pii")
            if doc_pii.get("enabled", True) else None
        )

    @staticmethod
    def _run(stage: str, guards: list[Guard], text: str, context: dict[str, Any] | None = None) -> GuardReport:
        report = GuardReport(stage=stage, original_text=text, text=text)
        for guard in guards:
            try:
                result = guard.check(report.text, context)
            except Exception as exc:  # a broken guard flags for human review rather than failing open silently
                logger.exception("Guard %s crashed", guard.name)
                result = GuardResult(guard.name, False, GuardAction.FLAG, f"Guard error: {exc}")
            report.results.append(result)
            if result.modified_text is not None:
                report.text = result.modified_text
            if result.action == GuardAction.BLOCK and not result.passed:
                break
        return report

    def run_input(self, query: str) -> GuardReport:
        return self._run("input", self.input_guards, query)

    def run_output(self, answer: str, contexts: list[str]) -> GuardReport:
        return self._run("output", self.output_guards, answer, {"contexts": contexts, "n_contexts": len(contexts)})

    def run_ingest_file(self, filename: str, size_bytes: int) -> GuardReport:
        return self._run("ingest", self.ingest_file_guards, filename, {"size_bytes": size_bytes})

    def run_ingest_content(self, text: str) -> GuardReport:
        return self._run("ingest", self.ingest_content_guards, text)

    def sanitize_document_text(self, text: str) -> tuple[str, GuardResult | None]:
        """Apply document PII policy to one page of text."""
        if self._doc_pii is None or not text:
            return text, None
        result = self._doc_pii.check(text)
        return (result.modified_text if result.modified_text is not None else text), result
