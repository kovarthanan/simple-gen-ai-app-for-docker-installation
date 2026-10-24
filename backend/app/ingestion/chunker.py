"""Recursive text splitter with overlap. Keeps page numbers so citations can point to them."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.ingestion.loaders import LoadedPage

_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "]


@dataclass
class Chunk:
    id: str  # deterministic UUID -> used as Qdrant point id and Neo4j Chunk id
    doc_id: str
    text: str
    index: int
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_recursive(text: str, size: int, separators: list[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    if not separators:
        return [text[i : i + size] for i in range(0, len(text), size)]
    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)
    if len(parts) == 1:
        return _split_recursive(text, size, rest)
    pieces: list[str] = []
    for i, part in enumerate(parts):
        piece = part + (sep if i < len(parts) - 1 else "")
        if not piece:
            continue
        if len(piece) > size:
            pieces.extend(_split_recursive(piece, size, rest))
        else:
            pieces.append(piece)
    return pieces


def _merge(pieces: list[str], size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > size:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            if " " in tail:  # start the overlap on a word boundary
                tail = tail[tail.index(" ") + 1 :]
            current = tail + piece
        else:
            current += piece
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def chunk_document(
    doc_id: str,
    pages: list[LoadedPage],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    base_metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    chunks: list[Chunk] = []
    for page in pages:
        text = normalize_whitespace(page.text or "")
        if not text:
            continue
        for piece in _merge(_split_recursive(text, chunk_size, _SEPARATORS), chunk_size, chunk_overlap):
            index = len(chunks)
            chunks.append(
                Chunk(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{index}")),
                    doc_id=doc_id,
                    text=piece,
                    index=index,
                    page=page.page,
                    metadata=dict(base_metadata or {}),
                )
            )
    return chunks
