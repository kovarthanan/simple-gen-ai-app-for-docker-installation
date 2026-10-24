"""Sidebar: backend status, search settings and reviewer access (shared by every page)."""
from __future__ import annotations

import streamlit as st

from components.guardrail_badge import chip
from config import BACKEND_URL, REVIEWER_API_KEY
from services.api_client import ApiError, cached_health

DEFAULTS = {
    "rs_top_k": 5, "rs_graph_depth": 1, "rs_final_k": 8, "rs_use_vector": True, "rs_use_graph": True,
    "reviewer_key": REVIEWER_API_KEY, "reviewer_name": "",
}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)


def status_html() -> str:
    try:
        health = cached_health()
    except ApiError:
        return chip("Backend offline", "block", dot=True, title=BACKEND_URL)
    checks = health.get("checks", {})
    names = {"vector_store": "Qdrant", "graph_store": "Neo4j", "llm": "LLM", "database": "App DB"}
    parts = []
    for key, label in names.items():
        value = str(checks.get(key, ""))
        ok = value in ("ok", "configured")
        parts.append(chip(label, "ok" if ok else "block", dot=True, title=value))
    return "".join(parts)


def render_sidebar() -> None:
    init_state()
    with st.sidebar:
        st.html(f'<div style="margin:.4rem 0 .2rem">{status_html()}</div>')

        with st.expander("Search settings", icon=":material/tune:"):
            st.toggle("Search passages", key="rs_use_vector",
                      help="Semantic search over document chunks in Qdrant")
            st.toggle("Search knowledge graph", key="rs_use_graph",
                      help="Look up entities in Neo4j and follow their relationships")
            st.slider("Passages to retrieve", 1, 20, key="rs_top_k")
            st.slider("Graph hops", 1, 3, key="rs_graph_depth",
                      help="How far to follow relationships from matched entities")
            st.slider("Items sent to the LLM", 2, 20, key="rs_final_k")

        with st.expander("Reviewer access", icon=":material/verified_user:",
                         expanded=not st.session_state.get("reviewer_key")):
            st.text_input("Reviewer key", type="password", key="reviewer_key",
                          help="REVIEWER_API_KEY from the backend .env")
            st.text_input("Your name", key="reviewer_name", placeholder="Shown in the activity log")
        st.caption(f"Backend: {BACKEND_URL}")


def retrieval_payload() -> dict:
    s = st.session_state
    return {"top_k": s.rs_top_k, "graph_depth": s.rs_graph_depth, "final_top_k": s.rs_final_k,
            "use_vector": s.rs_use_vector, "use_graph": s.rs_use_graph}
