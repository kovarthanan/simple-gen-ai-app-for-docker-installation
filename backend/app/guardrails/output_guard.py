"""Output guards for LLM answers: groundedness, citations, toxicity, PII leakage."""
from __future__ import annotations

import re
from typing import Any

from app.guardrails.base import Guard, GuardAction, GuardResult
from app.guardrails.groundedness import GroundednessScorer, is_abstention
from app.guardrails.input_guard import PIIGuard

_CITATION_GROUP = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def parse_citations(text: str, n_contexts: int | None = None) -> list[int]:
    found: set[int] = set()
    for group in _CITATION_GROUP.findall(text):
        for num in group.split(","):
            value = int(num.strip())
            if n_contexts is None or 1 <= value <= n_contexts:
                found.add(value)
    return sorted(found)


class GroundednessGuard(Guard):
    name = "groundedness"

    def __init__(self, scorer: GroundednessScorer, min_score: float = 0.7):
        self.scorer = scorer
        self.min_score = min_score

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        contexts = (context or {}).get("contexts", [])
        res = self.scorer.score(text, contexts)
        meta = {"supported": res.supported, "total": res.total, "unsupported": res.unsupported[:5],
                "method": res.method, "abstained": res.abstained}
        if res.score < self.min_score:
            return GuardResult(self.name, False, GuardAction.FLAG,
                               f"Only {res.supported}/{res.total} sentences are supported by the context",
                               score=res.score, metadata=meta)
        return GuardResult(self.name, True, score=res.score, metadata=meta)


class CitationGuard(Guard):
    name = "citations"

    def __init__(self, required: bool = True):
        self.required = required

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        n = (context or {}).get("n_contexts", 0)
        if not self.required or n == 0 or is_abstention(text):
            return GuardResult.ok(self.name)
        all_numbers = parse_citations(text)
        valid = [c for c in all_numbers if 1 <= c <= n]
        invalid = [c for c in all_numbers if c not in valid]
        if not valid:
            return GuardResult(self.name, False, GuardAction.FLAG, "Answer has no valid citations")
        if invalid:
            return GuardResult(self.name, False, GuardAction.FLAG,
                               f"Answer cites non-existent sources {invalid}", metadata={"invalid": invalid})
        return GuardResult.ok(self.name, citations=valid)


class ToxicityGuard(Guard):
    """Keyword-based placeholder. Swap in a classifier (e.g. Detoxify, Llama Guard) for production."""

    name = "toxicity"

    def __init__(self, keywords: list[str], action: str = "flag"):
        self.action = GuardAction(action)
        self.patterns = [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in keywords if k]

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        hits = [p.pattern for p in self.patterns if p.search(text)]
        if hits:
            return GuardResult(self.name, False, self.action, "Answer contains disallowed language",
                               score=min(1.0, 0.5 * len(hits)), metadata={"matched": hits})
        return GuardResult.ok(self.name, score=0.0)


def build_output_guards(cfg: dict[str, Any], scorer: GroundednessScorer, use_presidio: bool = False) -> list[Guard]:
    guards: list[Guard] = []
    g = cfg.get("groundedness", {})
    if g.get("enabled", True):
        guards.append(GroundednessGuard(scorer, g.get("min_score", 0.7)))
    guards.append(CitationGuard(cfg.get("citations", {}).get("required", True)))
    tox = cfg.get("toxicity", {})
    if tox.get("enabled", True) and tox.get("keywords"):
        guards.append(ToxicityGuard(tox["keywords"], tox.get("action", "flag")))
    pii = cfg.get("pii", {})
    if pii.get("enabled", True):
        guards.append(PIIGuard(pii.get("action", "redact"), pii.get("entities"), use_presidio, name="output_pii"))
    return guards
