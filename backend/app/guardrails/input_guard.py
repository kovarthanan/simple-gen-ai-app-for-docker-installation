"""Input guards for user questions: length, prompt injection, PII, blocked topics."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.guardrails.base import Guard, GuardAction, GuardResult
from app.guardrails.pii import redact_pii

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|system|your)\b.{0,20}\b(instructions?|prompts?|rules|directions|guidelines)",
    r"\b(reveal|show|print|repeat|output|leak|tell me)\b.{0,30}\b(system|hidden|initial|original)\s+(prompt|instructions?|message)",
    r"\byou are now\b.{0,40}\b(unrestricted|jailbroken|dan|evil|without (rules|restrictions|limits))",
    r"\b(act|behave|pretend|roleplay)\b.{0,20}\b(as|to be|like)\b.{0,40}\b(no|without)\s+(rules|restrictions|filters|limits|guidelines)",
    r"\bdo anything now\b|\bDAN mode\b|\bdeveloper mode\b|\bjailbreak\b",
    r"\bbypass\b.{0,30}\b(safety|guardrails?|filters?|restrictions?|content policy)",
    r"</?\s*(system|assistant|instructions?)\s*>",
    r"\bnew (system )?instructions?\s*:",
]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")  # zero-width chars
    return re.sub(r"\s+", " ", text)


class LengthGuard(Guard):
    name = "length"

    def __init__(self, min_length: int = 1, max_length: int = 4000):
        self.min_length, self.max_length = min_length, max_length

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        n = len(text.strip())
        if n < self.min_length:
            return GuardResult(self.name, False, GuardAction.BLOCK, f"Input is too short ({n} chars)")
        if n > self.max_length:
            return GuardResult(self.name, False, GuardAction.BLOCK,
                               f"Input is too long ({n} > {self.max_length} chars)")
        return GuardResult.ok(self.name)


class PromptInjectionGuard(Guard):
    name = "prompt_injection"

    def __init__(self, block_threshold: float = 0.5, extra_patterns: list[str] | None = None,
                 action: GuardAction = GuardAction.BLOCK):
        self.threshold = block_threshold
        self.action = action
        self.patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS + list(extra_patterns or [])]

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        normalized = _normalize(text)
        hits = [p.pattern for p in self.patterns if p.search(normalized)]
        score = min(1.0, 0.6 * len(hits))
        if hits and score >= self.threshold:
            return GuardResult(self.name, False, self.action,
                               f"Possible prompt injection ({len(hits)} pattern(s) matched)",
                               score=score, metadata={"patterns": hits})
        return GuardResult.ok(self.name, score=score)


class PIIGuard(Guard):
    name = "pii"

    def __init__(self, action: str = "redact", entities: list[str] | None = None,
                 use_presidio: bool = False, name: str | None = None):
        self.action = GuardAction(action)
        self.entities = entities
        self.use_presidio = use_presidio
        if name:
            self.name = name

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        redacted, matches = redact_pii(text, self.entities, self.use_presidio)
        if not matches:
            return GuardResult.ok(self.name)
        types = sorted({m.entity_type for m in matches})
        reason = f"PII detected: {', '.join(types)}"
        meta = {"pii_types": types, "count": len(matches)}
        if self.action == GuardAction.REDACT:
            return GuardResult(self.name, True, GuardAction.REDACT, reason, modified_text=redacted, metadata=meta)
        if self.action == GuardAction.ALLOW:
            return GuardResult(self.name, True, GuardAction.ALLOW, reason, metadata=meta)
        return GuardResult(self.name, False, self.action, reason, metadata=meta)


class BlockedTopicGuard(Guard):
    name = "blocked_topics"

    def __init__(self, keywords: list[str], action: str = "block"):
        self.action = GuardAction(action)
        self.patterns = [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in keywords if k]

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        hits = [p.pattern for p in self.patterns if p.search(text)]
        if hits:
            return GuardResult(self.name, False, self.action, "Question touches a blocked topic",
                               metadata={"matched": hits})
        return GuardResult.ok(self.name)


def build_input_guards(cfg: dict[str, Any], use_presidio: bool = False) -> list[Guard]:
    guards: list[Guard] = [LengthGuard(cfg.get("min_length", 1), cfg.get("max_length", 4000))]
    inj = cfg.get("prompt_injection", {})
    if inj.get("enabled", True):
        guards.append(PromptInjectionGuard(inj.get("block_threshold", 0.5), inj.get("extra_patterns")))
    topics = cfg.get("blocked_topics", {})
    if topics.get("keywords"):
        guards.append(BlockedTopicGuard(topics["keywords"], topics.get("action", "block")))
    pii = cfg.get("pii", {})
    if pii.get("enabled", True):
        guards.append(PIIGuard(pii.get("action", "redact"), pii.get("entities"), use_presidio))
    return guards
