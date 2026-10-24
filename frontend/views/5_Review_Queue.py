"""Review queue: pick an item on the left, decide on the right."""
from __future__ import annotations

import streamlit as st

from components.metric_cards import metric_row
from components.review_card import item_title, render_review_card
from components.theme import card, empty_state, page_header, panel, panel_title
from services.api_client import ApiError, get_client

ICONS = {"answer": ":material/forum:", "entity": ":material/label:", "relation": ":material/share:"}
FILTERS = {"All": None, "Answers": "answer", "Entities": "entity", "Relationships": "relation"}

page_header("Review queue", "Things the system wasn't sure about. Approved facts go into the knowledge graph, "
                            "and approved answers are shown to the person who asked.")

if not st.session_state.get("reviewer_key"):
    with card("needkey"):
        empty_state("Enter the reviewer key to start reviewing",
                    "Open Reviewer access in the sidebar and paste REVIEWER_API_KEY from the backend .env file.")
    st.stop()

api = get_client()
try:
    stats = api.review_stats()
except ApiError as exc:
    st.error(exc.message)
    st.stop()

by_type = stats.get("pending_by_type") or {}
metric_row([
    {"label": "Answers to check", "value": by_type.get("answer", 0), "tone": "review"},
    {"label": "Entities to check", "value": by_type.get("entity", 0), "tone": "kg"},
    {"label": "Relationships to check", "value": by_type.get("relation", 0), "tone": "kg"},
    {"label": "Decided so far", "value": stats.get("approved", 0) + stats.get("edited", 0) + stats.get("rejected", 0),
     "tone": "ok", "hint": f'{stats.get("rejected", 0)} rejected'},
])

choice = st.segmented_control("Show", list(FILTERS), default="All", key="review_filter",
                              label_visibility="collapsed") or "All"
try:
    pending = api.review_pending(FILTERS[choice], limit=200)
except ApiError as exc:
    st.error(exc.message)
    st.stop()
items = pending["items"]

left, right = st.columns([1, 1.75], gap="medium")
with left:
    with panel("queue", 292):
        panel_title(f"{pending['total']} waiting", "Oldest first")
        if not items:
            empty_state("All caught up", "New items appear here when an answer or extracted fact needs a check.")
        ids = [i["id"] for i in items]
        if st.session_state.get("review_selected") not in ids:
            st.session_state.review_selected = ids[0] if ids else None
        for it in items:
            conf = f'  {it["confidence"]:.0%}' if it.get("confidence") is not None else ""
            title = item_title(it)
            label = (title[:58] + "…" if len(title) > 59 else title) + conf
            selected = st.session_state.review_selected == it["id"]
            if st.button(label, key=f"pick_{it['id']}", icon=ICONS.get(it["item_type"]),
                         type="primary" if selected else "secondary", use_container_width=True):
                st.session_state.review_selected = it["id"]
                st.rerun()
with right:
    with panel("detail", 292):
        current = next((i for i in items if i["id"] == st.session_state.get("review_selected")), None)
        if current:
            render_review_card(current)
        else:
            empty_state("Nothing selected", "Pick an item from the list to review it.")
