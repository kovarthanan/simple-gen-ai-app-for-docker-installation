"""Chat message rendering. Citation markers like [2] become pills coloured by source."""
from __future__ import annotations

import html
import re

import streamlit as st

from components.guardrail_badge import status_chip

_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def answer_html(text: str, contexts: list[dict]) -> str:
    """Escape the answer, then turn [n] into coloured citation pills (blue = passage, saffron = graph)."""
    origin = {c.get("citation"): c.get("origin") for c in contexts or []}
    safe = html.escape(text or "").replace("\n", "<br>")

    def pill(match: re.Match) -> str:
        parts = []
        for num in match.group(1).split(","):
            n = int(num.strip())
            kind = {"vector": "cite-vec", "graph": "cite-kg"}.get(origin.get(n), "cite-none")
            parts.append(f'<span class="cite {kind}" title="Source {n}">{n}</span>')
        return "".join(parts)

    return f'<div style="line-height:1.6;font-size:.95rem">{_CITE.sub(pill, safe)}</div>'


def render_message(msg: dict) -> None:
    if msg["role"] == "user":
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(msg["content"])
        return

    resp = msg.get("response") or {}
    with st.chat_message("assistant", avatar=":material/hub:"):
        status = resp.get("status")
        if status == "answered" and resp.get("answer"):
            st.html(answer_html(resp["answer"], resp.get("contexts")))
            if resp.get("reviewed"):
                st.html('<span class="chip chip-ok"><span class="dot"></span>Checked by a reviewer</span>')
        elif status == "pending_review":
            st.html(status_chip(status))
            if resp.get("answer"):  # backend configured to show unverified drafts
                st.html(answer_html(resp["answer"], resp.get("contexts")))
            st.caption(resp.get("message") or "A reviewer needs to check this answer before it's shown.")
        elif status == "blocked":
            st.html(status_chip(status))
            st.caption(resp.get("message") or "This question was blocked by a safety check.")
        elif status == "rejected":
            st.html(status_chip(status))
            st.caption(resp.get("message") or "A reviewer rejected this answer.")
        else:
            st.markdown(msg.get("content") or "")
            if msg.get("error"):
                st.caption(msg["error"])
