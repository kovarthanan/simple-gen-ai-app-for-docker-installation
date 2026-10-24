"""Guard interface, result type and policy loading."""
from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class GuardAction(str, Enum):
    ALLOW = "allow"    # nothing to do
    REDACT = "redact"  # text was modified (e.g. PII removed) but processing continues
    FLAG = "flag"      # continue, but mark for human review
    BLOCK = "block"    # stop processing


@dataclass
class GuardResult:
    guard: str
    passed: bool
    action: GuardAction = GuardAction.ALLOW
    reason: str | None = None
    score: float | None = None
    modified_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, guard: str, score: float | None = None, **metadata: Any) -> "GuardResult":
        return cls(guard=guard, passed=True, score=score, metadata=metadata)


class Guard(ABC):
    name: str = "guard"

    @abstractmethod
    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult: ...


# --- Policy -------------------------------------------------------------------------
DEFAULT_POLICY: dict[str, Any] = {
    "use_presidio": False,
    "input": {
        "min_length": 2,
        "max_length": 4000,
        "prompt_injection": {"enabled": True, "block_threshold": 0.5, "extra_patterns": []},
        "pii": {"enabled": True, "action": "redact", "entities": None},
        "blocked_topics": {"action": "block", "keywords": []},
    },
    "output": {
        "groundedness": {"enabled": True, "min_score": 0.7, "sentence_threshold": 0.5},
        "citations": {"required": True},
        "toxicity": {"enabled": True, "action": "flag", "keywords": []},
        "pii": {"enabled": True, "action": "redact", "entities": None},
    },
    "ingest": {
        "allowed_extensions": [".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm"],
        "max_file_mb": 20,
        "min_text_chars": 20,
        "pii": {"enabled": True, "action": "redact", "entities": None},
        "prompt_injection": {"enabled": True, "action": "flag", "block_threshold": 0.5},
    },
    "hitl": {
        "answer_review_below_confidence": 0.6,
        "review_on_guard_flags": ["groundedness", "citations", "toxicity", "prompt_injection"],
        "hold_answers_pending_review": True,
        "entity_auto_approve_above": 0.8,
        "entity_drop_below": 0.3,
        "negative_feedback_to_review": True,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_policy(path: str | None) -> dict[str, Any]:
    """Load policies.yaml (resolved relative to cwd, then to the backend/ folder) over the defaults."""
    if not path:
        return copy.deepcopy(DEFAULT_POLICY)
    candidate = Path(path)
    if not candidate.is_absolute() and not candidate.exists():
        candidate = Path(__file__).resolve().parents[2] / path
    if not candidate.exists():
        return copy.deepcopy(DEFAULT_POLICY)
    with candidate.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return deep_merge(DEFAULT_POLICY, data)
