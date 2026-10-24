"""Ingestion guards: file type/size, minimum content, instructions hidden in documents."""
from __future__ import annotations

from typing import Any

from app.guardrails.base import Guard, GuardAction, GuardResult
from app.guardrails.input_guard import PromptInjectionGuard
from app.ingestion.loaders import file_extension


class FileTypeGuard(Guard):
    name = "file_type"

    def __init__(self, allowed_extensions: list[str]):
        self.allowed = {e.lower() for e in allowed_extensions}

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        ext = file_extension(text)
        if ext not in self.allowed:
            return GuardResult(self.name, False, GuardAction.BLOCK,
                               f"File type '{ext or 'none'}' is not allowed")
        return GuardResult.ok(self.name)


class FileSizeGuard(Guard):
    name = "file_size"

    def __init__(self, max_mb: float):
        self.max_bytes = int(max_mb * 1024 * 1024)

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        size = int((context or {}).get("size_bytes", 0))
        if size == 0:
            return GuardResult(self.name, False, GuardAction.BLOCK, "File is empty")
        if size > self.max_bytes:
            return GuardResult(self.name, False, GuardAction.BLOCK,
                               f"File is {size / 1048576:.1f} MB; limit is {self.max_bytes / 1048576:.0f} MB")
        return GuardResult.ok(self.name)


class MinContentGuard(Guard):
    name = "min_content"

    def __init__(self, min_chars: int = 20):
        self.min_chars = min_chars

    def check(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        n = len(text.strip())
        if n < self.min_chars:
            return GuardResult(self.name, False, GuardAction.BLOCK,
                               f"Only {n} characters of text could be extracted (scanned PDF? try OCR)")
        return GuardResult.ok(self.name)


def build_ingest_file_guards(cfg: dict[str, Any]) -> list[Guard]:
    return [FileTypeGuard(cfg.get("allowed_extensions", [])), FileSizeGuard(cfg.get("max_file_mb", 20))]


def build_ingest_content_guards(cfg: dict[str, Any]) -> list[Guard]:
    guards: list[Guard] = [MinContentGuard(cfg.get("min_text_chars", 20))]
    inj = cfg.get("prompt_injection", {})
    if inj.get("enabled", True):
        # Documents with LLM-directed instructions are flagged (not blocked) by default;
        # the RAG prompt already tells the model to treat context as data.
        guards.append(PromptInjectionGuard(inj.get("block_threshold", 0.5), inj.get("extra_patterns"),
                                           action=GuardAction(inj.get("action", "flag"))))
    return guards
