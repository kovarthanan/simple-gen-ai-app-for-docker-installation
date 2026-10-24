"""Chips for answer status and guardrail results."""
from __future__ import annotations

import html

GUARD_NAMES = {
    "length": "Length", "prompt_injection": "Prompt injection", "pii": "Personal data",
    "blocked_topics": "Blocked topics", "groundedness": "Grounded in sources", "citations": "Citations",
    "toxicity": "Language", "output_pii": "Personal data in answer", "file_type": "File type",
    "file_size": "File size", "min_content": "Readable text", "document_pii": "Personal data",
}

STATUS = {
    "answered": ("Answered", "ok"),
    "pending_review": ("Waiting for review", "review"),
    "blocked": ("Blocked", "block"),
    "rejected": ("Rejected by reviewer", "neutral"),
    "indexed": ("Indexed", "ok"),
    "indexed_pending_review": ("Indexed, items to review", "review"),
    "processing": ("Processing", "neutral"),
    "failed": ("Failed", "block"),
    "approved": ("Approved", "ok"),
    "edited": ("Approved with edits", "ok"),
    "pending": ("Pending", "review"),
}


def chip(text: str, tone: str = "neutral", dot: bool = False, title: str | None = None) -> str:
    t = f' title="{html.escape(title)}"' if title else ""
    d = '<span class="dot"></span>' if dot else ""
    return f'<span class="chip chip-{tone}"{t}>{d}{html.escape(text)}</span>'


def status_chip(status: str) -> str:
    label, tone = STATUS.get(status, (status.replace("_", " ").capitalize(), "neutral"))
    return chip(label, tone, dot=True)


def guard_flag_chip(flag: dict) -> str:
    name = GUARD_NAMES.get(flag.get("guard", ""), flag.get("guard", "").replace("_", " ").capitalize())
    action, passed = flag.get("action"), flag.get("passed")
    reason = flag.get("reason") or ""
    if action == "block" and not passed:
        return chip(f"{name}: blocked", "block", title=reason)
    if action == "flag" and not passed:
        return chip(f"{name}: flagged", "review", title=reason)
    if action == "redact":
        return chip(f"{name}: removed", "vec", title=reason)
    return chip(name, "ok", title=reason or "Passed")


def guard_flags_html(flags: list[dict]) -> str:
    if not flags:
        return '<span class="muted">No checks ran.</span>'
    order = {"block": 0, "flag": 1, "redact": 2}
    flags = sorted(flags, key=lambda f: (order.get(f.get("action"), 3) if not f.get("passed") or f.get("action") == "redact" else 4))
    return "".join(guard_flag_chip(f) for f in flags)
