"""Rules that decide when a human must review something."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.graph.base import Entity, Relation, normalize_key
from app.guardrails.runner import GuardReport

EntityRoute = Literal["auto", "review", "drop"]


@dataclass
class ReviewDecision:
    needs_review: bool
    reasons: list[str] = field(default_factory=list)


class HITLPolicy:
    def __init__(self, cfg: dict[str, Any], confidence_override: float | None = None):
        self.answer_threshold = (
            confidence_override if confidence_override is not None
            else float(cfg.get("answer_review_below_confidence", 0.6))
        )
        self.review_on_flags = set(cfg.get("review_on_guard_flags", []))
        self.hold_answers = bool(cfg.get("hold_answers_pending_review", True))
        self.entity_auto = float(cfg.get("entity_auto_approve_above", 0.8))
        self.entity_drop = float(cfg.get("entity_drop_below", 0.3))
        self.negative_feedback_to_review = bool(cfg.get("negative_feedback_to_review", True))

    # -- answers ------------------------------------------------------------------
    def review_answer(self, confidence: float, output_report: GuardReport) -> ReviewDecision:
        reasons = []
        if confidence < self.answer_threshold:
            reasons.append(f"confidence {confidence:.2f} < {self.answer_threshold:.2f}")
        for guard in output_report.flagged_guards:
            if guard in self.review_on_flags:
                result = output_report.get(guard)
                reasons.append(f"{guard}: {result.reason if result else 'flagged'}")
        return ReviewDecision(bool(reasons), reasons)

    # -- knowledge graph -------------------------------------------------------------
    def route_entity(self, entity: Entity) -> EntityRoute:
        if entity.confidence >= self.entity_auto:
            return "auto"
        if entity.confidence < self.entity_drop:
            return "drop"
        return "review"

    def route_relation(self, relation: Relation, auto_keys: set[str], dropped_keys: set[str]) -> EntityRoute:
        s, o = normalize_key(relation.subject), normalize_key(relation.object)
        if relation.confidence < self.entity_drop or s in dropped_keys or o in dropped_keys:
            return "drop"
        if relation.confidence >= self.entity_auto and s in auto_keys and o in auto_keys:
            return "auto"
        return "review"
