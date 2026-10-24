"""Ask: chat on the left, evidence for the selected answer on the right."""
from __future__ import annotations

import streamlit as st

from components.chat import render_message
from components.feedback_widget import feedback_widget
from components.sidebar import retrieval_payload
from components.sources import render_evidence
from components.theme import empty_state, page_header, panel, panel_title
from config import REVIEW_THRESHOLD
from services.api_client import ApiError, clear_cache, get_client

st.session_state.setdefault("chat", [])
st.session_state.setdefault("selected_answer", None)

SUGGESTIONS = [
    "Summarize the main topics in my documents",
    "Which people and organizations are mentioned?",
    "How are the key entities related to each other?",
]


def ask(question: str) -> None:
    chat = st.session_state.chat
    chat.append({"role": "user", "content": question})
    try:
        resp = get_client().query({"query": question, **retrieval_payload()})
        chat.append({"role": "assistant", "response": resp})
    except ApiError as exc:
        chat.append({"role": "assistant", "content": "I couldn't answer that.", "error": exc.message})
    st.session_state.selected_answer = len(chat) - 1
    clear_cache()


def refresh(index: int) -> None:
    msg = st.session_state.chat[index]
    try:
        msg["response"] = get_client().get_query(msg["response"]["query_id"])
    except ApiError as exc:
        st.toast(exc.message, icon=":material/error:")
        return
    status = msg["response"]["status"]
    st.toast({"answered": "A reviewer approved this answer.", "rejected": "A reviewer rejected this answer."}
             .get(status, "Still waiting for a reviewer."), icon=":material/rule:")


head, action = st.columns([6, 1], vertical_alignment="bottom")
with head:
    page_header("Ask", "Answers cite their sources inline: blue numbers are document passages, "
                       "amber numbers are knowledge-graph facts.")
with action:
    if st.button("New chat", icon=":material/add_comment:", use_container_width=True,
                 disabled=not st.session_state.chat):
        st.session_state.chat, st.session_state.selected_answer = [], None
        st.rerun()

left, right = st.columns([1.3, 1], gap="medium")
pending_prompt = None

with left:
    with panel("chat", 235):
        chat = st.session_state.chat
        if not chat:
            empty_state("Ask anything about the documents you've added",
                        "The answer comes with the passages and graph facts it used, so you can check it.")
            cols = st.columns(len(SUGGESTIONS))
            for col, text in zip(cols, SUGGESTIONS):
                if col.button(text, use_container_width=True, key=f"sugg_{text}"):
                    pending_prompt = text
        for i, msg in enumerate(chat):
            render_message(msg)
            resp = msg.get("response")
            if msg["role"] != "assistant" or not resp:
                continue
            a, b, c = st.columns([1.1, 1.2, 2.2], vertical_alignment="center")
            with a:
                if resp.get("status") in ("answered", "pending_review"):
                    feedback_widget(resp["query_id"])
            with b:
                selected = st.session_state.selected_answer == i
                if st.button("Showing evidence" if selected else "Show evidence", key=f"ev_{i}",
                             icon=":material/fact_check:", type="tertiary", disabled=selected):
                    st.session_state.selected_answer = i
                    st.rerun()
            with c:
                if resp.get("status") == "pending_review":
                    if st.button("Check for a decision", key=f"chk_{i}", icon=":material/refresh:", type="tertiary"):
                        refresh(i)
                        st.rerun()
    prompt = st.chat_input("Ask about your documents")

with right:
    with panel("evidence", 148):
        panel_title("Evidence")
        idx = st.session_state.selected_answer
        chat = st.session_state.chat
        selected = chat[idx].get("response") if idx is not None and idx < len(chat) else None
        render_evidence(selected, REVIEW_THRESHOLD)

question = prompt or pending_prompt
if question:
    with left:
        with st.spinner("Searching passages and the knowledge graph"):
            ask(question)
    st.rerun()
