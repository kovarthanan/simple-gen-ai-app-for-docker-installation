"""Thumbs up/down on an answer. A thumbs-down sends the answer back to the review queue."""
from __future__ import annotations

import streamlit as st

from services.api_client import ApiError, clear_cache, get_client


def feedback_widget(query_id: str) -> None:
    sent_key = f"fb_sent_{query_id}"
    if st.session_state.get(sent_key):
        st.caption(st.session_state[sent_key])
        return
    choice = st.feedback("thumbs", key=f"fb_{query_id}")
    if choice is None:
        return
    rating = 1 if choice == 1 else -1
    try:
        result = get_client().send_feedback(query_id, rating)
    except ApiError as exc:
        st.caption(f"Feedback not saved: {exc.message}")
        return
    clear_cache()
    if result.get("sent_to_review"):
        msg = "Thanks. This answer was sent to a reviewer."
    else:
        msg = "Thanks for the feedback."
    st.session_state[sent_key] = msg
    st.toast(msg, icon=":material/thumb_up:" if rating > 0 else ":material/flag:")
    st.rerun()
