"""Knowledge base: metadata for the vector DB and the knowledge graph side by side."""
from __future__ import annotations

import streamlit as st

from components.graph_metadata import render_graph_metadata
from components.theme import page_header, panel
from components.vector_metadata import render_vector_metadata
from services.api_client import ApiError, clear_cache, get_client

head, action = st.columns([6, 1], vertical_alignment="bottom")
with head:
    page_header("Knowledge base", "What's stored in each database. Blue is the vector database, "
                                  "amber is the knowledge graph.")
with action:
    if st.button("Refresh", icon=":material/refresh:", use_container_width=True):
        clear_cache()

api = get_client()
left, right = st.columns(2, gap="medium")
with left:
    with panel("vec", 142):
        try:
            render_vector_metadata(api.vector_metadata())
        except ApiError as exc:
            st.error(exc.message)
with right:
    with panel("kg", 142):
        try:
            render_graph_metadata(api.graph_metadata(top_n=8))
        except ApiError as exc:
            st.error(exc.message)
