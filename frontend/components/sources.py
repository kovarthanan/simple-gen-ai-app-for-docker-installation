"""Evidence panel: passages and graph facts used for an answer, plus checks and timings."""
from __future__ import annotations

import html
import re

import streamlit as st

from components.guardrail_badge import GUARD_NAMES, guard_flags_html, status_chip
from components.metric_cards import meter_html
from components.theme import empty_state

_FACT = re.compile(r"^(.*?) -\[(.+?)\]-> (.*)$")


def _fact_html(content: str) -> str:
    m = _FACT.match(content)
    if not m:
        return html.escape(content)
    s, p, o = (html.escape(x) for x in m.groups())
    return f'<span class="fact">{s}<span class="pred">{p.replace("_", " ").lower()}</span>{o}</span>'


def evidence_item_html(ctx: dict) -> str:
    vec = ctx.get("origin") == "vector"
    meta = ctx.get("metadata") or {}
    num = ctx.get("citation")
    cls = "ev ev-vec" if vec else "ev ev-kg"
    if ctx.get("cited"):
        cls += " cited"
    badge = f'<span class="cite {"cite-vec" if vec else "cite-kg"}">{num}</span>' if num else ""
    if vec:
        where = html.escape(str(meta.get("source") or "document"))
        if meta.get("page") is not None:
            where += f", page {meta['page']}"
        right = f"similarity {ctx.get('source_score', 0):.2f}"
        body = html.escape(ctx.get("content", ""))
    else:
        hops = meta.get("hops", 1)
        where = "Knowledge graph"
        right = f"{hops} hop{'s' if hops != 1 else ''}, confidence {ctx.get('source_score', 0):.2f}"
        body = _fact_html(ctx.get("content", ""))
    used = ' <b style="color:inherit">cited</b>' if ctx.get("cited") else ""
    return (f'<div class="{cls}"><div class="ev-head"><span>{badge} {where}{used}</span>'
            f'<span>#{ctx.get("rank", "–")} after merge, {right}</span></div>'
            f'<div class="ev-body">{body}</div></div>')


def render_evidence(resp: dict | None, threshold: float) -> None:
    if not resp:
        empty_state("Evidence shows up here",
                    "Ask a question and you'll see which passages and graph facts the answer used.")
        return

    contexts = resp.get("contexts") or []
    passages = [c for c in contexts if c.get("origin") == "vector"]
    facts = [c for c in contexts if c.get("origin") == "graph"]

    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.html(meter_html(resp.get("confidence"), threshold, "Confidence")
                + meter_html(resp.get("groundedness"), 0.7, "Grounded in sources"))
    with c2:
        entities = resp.get("matched_entities") or []
        ent = ", ".join(html.escape(e) for e in entities[:5]) or "none"
        st.html(f'<div style="text-align:right">{status_chip(resp.get("status", ""))}</div>'
                f'<div class="panel-sub" style="text-align:right;margin-top:6px">Graph entities matched: '
                f'<b style="color:var(--ink)">{ent}</b></div>')

    tabs = st.tabs([f"Passages ({len(passages)})", f"Graph facts ({len(facts)})", "Checks", "Timing"])
    with tabs[0]:
        if passages:
            st.html("".join(evidence_item_html(c) for c in passages))
        else:
            st.caption("No passages were used. Add documents, or turn passage search on in the sidebar.")
    with tabs[1]:
        if facts:
            st.html("".join(evidence_item_html(c) for c in facts))
        else:
            st.caption("No graph facts matched the entities in this question.")
    with tabs[2]:
        flags = resp.get("guard_flags") or []
        st.html(guard_flags_html(flags))
        problems = [f for f in flags if not f.get("passed") or f.get("action") == "redact"]
        for f in problems:
            name = GUARD_NAMES.get(f["guard"], f["guard"])
            st.html(f'<div class="row-item"><span><b>{html.escape(name)}</b></span>'
                    f'<span class="muted">{html.escape(f.get("reason") or "")}</span></div>')
    with tabs[3]:
        timing = resp.get("latency_ms") or {}
        names = {"input_guard": "Check question", "vector_retrieval": "Passage search",
                 "graph_retrieval": "Graph search", "fusion": "Merge results", "llm": "Write answer",
                 "output_guard": "Check answer", "total": "Total"}
        total = timing.get("total") or 1
        rows = []
        for key, label in names.items():
            if key not in timing:
                continue
            ms = timing[key]
            color = {"vector_retrieval": "var(--lapis)", "graph_retrieval": "var(--saffron)",
                     "total": "var(--ink)"}.get(key, "#9AA3B5")
            width = 100 if key == "total" else min(100, ms / total * 100)
            rows.append(f'<div class="meter-row" style="margin-top:6px"><span>{label}</span><span>{ms:,.0f} ms</span></div>'
                        f'<div class="meter" style="height:7px;margin:3px 0"><span style="width:{width:.0f}%;background:{color}"></span></div>')
        st.html("".join(rows) or '<span class="muted">No timing data.</span>')
