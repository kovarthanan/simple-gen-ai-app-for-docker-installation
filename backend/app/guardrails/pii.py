"""PII detection and redaction.

Regex detectors cover common global and Indian identifiers. Set `use_presidio: true`
in policies.yaml (and `pip install presidio-analyzer` + a spaCy model) to add
Microsoft Presidio's NER-based detection on top.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PIIMatch:
    entity_type: str
    start: int
    end: int
    value: str


# Order matters: earlier patterns win when matches overlap.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("CREDIT_CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    ("US_SSN", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    ("PHONE", re.compile(r"(?<![\w+])\+?\d[\d ().-]{8,16}\d(?!\w)")),
]
ALL_ENTITIES = [name for name, _ in _PATTERNS]


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_ANALYZER = None


def _presidio_matches(text: str) -> list[PIIMatch]:
    global _ANALYZER
    try:
        if _ANALYZER is None:
            from presidio_analyzer import AnalyzerEngine

            _ANALYZER = AnalyzerEngine()
        results = _ANALYZER.analyze(text=text, language="en")
    except Exception as exc:  # not installed / model missing
        logger.debug("Presidio unavailable: %s", exc)
        return []
    return [PIIMatch(r.entity_type, r.start, r.end, text[r.start : r.end]) for r in results if r.score >= 0.5]


def detect_pii(text: str, entities: list[str] | None = None, use_presidio: bool = False) -> list[PIIMatch]:
    wanted = set(entities) if entities else None
    matches: list[PIIMatch] = []
    taken: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in taken)

    for entity_type, pattern in _PATTERNS:
        if wanted and entity_type not in wanted:
            continue
        for m in pattern.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            value = m.group(0)
            digits = re.sub(r"\D", "", value)
            if entity_type == "CREDIT_CARD" and not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                continue
            if entity_type == "PHONE" and not 10 <= len(digits) <= 13:
                continue
            matches.append(PIIMatch(entity_type, m.start(), m.end(), value))
            taken.append((m.start(), m.end()))

    if use_presidio:
        for pm in _presidio_matches(text):
            if (wanted is None or pm.entity_type in wanted) and not overlaps(pm.start, pm.end):
                matches.append(pm)
                taken.append((pm.start, pm.end))
    return sorted(matches, key=lambda m: m.start)


def redact_pii(text: str, entities: list[str] | None = None, use_presidio: bool = False) -> tuple[str, list[PIIMatch]]:
    matches = detect_pii(text, entities, use_presidio)
    if not matches:
        return text, []
    out, last = [], 0
    for m in matches:
        out.append(text[last : m.start])
        out.append(f"[REDACTED_{m.entity_type}]")
        last = m.end
    out.append(text[last:])
    return "".join(out), matches
