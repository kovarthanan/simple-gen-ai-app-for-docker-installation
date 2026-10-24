"""Streamlit entrypoint: navigation, shared styles and sidebar, plus the Overview page.

Run:  streamlit run app.py   (from the frontend/ folder; backend on http://localhost:8000)
"""
from __future__ import annotations

import html

import streamlit as st

st.set_page_config(page_title="Hybrid RAG", page_icon=":material/hub:", layout="wide",
                   initial_sidebar_state="expanded")

from components.guardrail_badge import status_chip  # noqa: E402
from components.metric_cards import metric_row  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402
from components.theme import empty_state, inject_css, page_header, panel, panel_title  # noqa: E402
from services.api_client import ApiError, cached_summary, get_client  # noqa: E402

inject_css()

STEPS = [
    ("", "Check the question", "Blocks prompt injection and removes personal data"),
    ("vec", "Search passages", "Qdrant finds document chunks with a similar meaning"),
    ("kg", "Search the knowledge graph", "Neo4j finds entities in the question and follows their links"),
    ("", "Merge and rank", "Both result lists are combined with reciprocal rank fusion"),
    ("", "Write the answer", "The LLM answers using only that context, citing each source"),
    ("", "Check the answer", "Every sentence must be supported, and sources must be cited"),
    ("review", "Ask a person when unsure", "Low-confidence answers wait in the review queue"),
]


def overview() -> None:
    page_header("Ask your documents and see where every answer comes from",
                "Each question is answered from two sources at once: passages found by meaning and facts from "
                "the knowledge graph. Anything the system isn't sure about waits for a person to check.")
    try:
        s = cached_summary()
    except ApiError as exc:
        st.error(exc.message)
        return

    vec, kg = s.get("vector", {}), s.get("graph", {})
    rate = s.get("positive_feedback_rate")
    metric_row([
        {"label": "Documents", "value": s.get("documents_total", 0), "tone": "ink"},
        {"label": "Passages", "value": vec.get("vectors_count", s.get("chunks_total", 0)), "tone": "vec",
         "hint": "in the vector database"},
        {"label": "Entities", "value": kg.get("total_nodes", 0), "tone": "kg", "hint": "in the knowledge graph"},
        {"label": "Relationships", "value": kg.get("total_relationships", 0), "tone": "kg"},
        {"label": "Questions asked", "value": s.get("queries_total", 0), "tone": "ink"},
        {"label": "Waiting for review", "value": s.get("pending_reviews", 0), "tone": "review",
         "hint": f"{rate:.0%} rated helpful" if rate is not None else "no ratings yet"},
    ])
    st.html('<div style="height:6px"></div>')

    c1, c2, c3 = st.columns([1.05, 1.3, 0.85], gap="small")
    with c1:
        with panel("ov_flow", 298):
            panel_title("How an answer is made", "Steps 2 and 3 run at the same time.")
            st.html('<ol class="steps">' + "".join(
                f'<li class="{cls}"><div><b>{title}</b><span>{desc}</span></div></li>' for cls, title, desc in STEPS
            ) + "</ol>")
    with c2:
        with panel("ov_recent", 298):
            panel_title("Recent questions")
            try:
                history = get_client().history(limit=25)
            except ApiError as exc:
                history = []
                st.caption(exc.message)
            if not history:
                empty_state("No questions yet", "Go to Ask and try a question about your documents.")
            for q in history:
                conf = f'{q["confidence"]:.0%}' if q.get("confidence") is not None else "–"
                st.html(f'<div class="row-item"><span class="q">{html.escape(q["query"])}</span>'
                        f'<span style="display:flex;gap:8px;align-items:center;flex-shrink:0">'
                        f'<span class="muted" title="Confidence">{conf}</span>{status_chip(q["status"])}</span></div>')
    with c3:
        with panel("ov_next", 298):
            panel_title("Start here")
            st.page_link("views/1_Upload_Documents.py", label="Add documents", icon=":material/upload_file:")
            st.page_link("views/2_Chat.py", label="Ask a question", icon=":material/forum:")
            st.page_link("views/5_Review_Queue.py", label="Review uncertain items", icon=":material/rule:")
            st.page_link("views/3_Graph_Explorer.py", label="Explore the graph", icon=":material/hub:")
            by_type = s.get("reviews_by_type") or {}
            if by_type:
                names = {"answer": "answers", "entity": "entities", "relation": "relationships"}
                st.html('<div class="panel-sub" style="margin-top:12px">In the review queue</div>' + "".join(
                    f'<div class="row-item"><span>{names.get(k, k).capitalize()}</span><b>{v}</b></div>'
                    for k, v in by_type.items()))
            last = s.get("last_ingested_at")
            if last:
                st.caption(f"Last document added {str(last)[:16].replace('T', ' ')}")


def _review_title() -> str:
    try:
        pending = cached_summary().get("pending_reviews", 0)
    except ApiError:
        pending = 0
    return f"Review queue ({pending})" if pending else "Review queue"


nav = st.navigation({
    "Workspace": [
        st.Page(overview, title="Overview", icon=":material/space_dashboard:", default=True),
        st.Page("views/2_Chat.py", title="Ask", icon=":material/forum:", url_path="ask"),
        st.Page("views/1_Upload_Documents.py", title="Add documents", icon=":material/upload_file:", url_path="documents"),
    ],
    "Inspect": [
        st.Page("views/3_Graph_Explorer.py", title="Knowledge graph", icon=":material/hub:", url_path="graph"),
        st.Page("views/4_Metadata_Dashboard.py", title="Knowledge base", icon=":material/database:", url_path="knowledge-base"),
    ],
    "Review": [
        st.Page("views/5_Review_Queue.py", title=_review_title(), icon=":material/rule:", url_path="review"),
        st.Page("views/6_Feedback_Analytics.py", title="Feedback and activity", icon=":material/insights:", url_path="activity"),
    ],
})
render_sidebar()
nav.run()
