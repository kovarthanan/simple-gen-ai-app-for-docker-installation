"""Feedback and activity: how answers are landing, and what reviewers decided."""
from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

from components.guardrail_badge import STATUS
from components.metric_cards import metric_row
from components.theme import empty_state, page_header, panel, panel_title
from components.vector_metadata import chart_config
from config import COLORS
from services.api_client import ApiError, cached_summary, get_client

page_header("Feedback and activity", "How people rate answers, how often the safety checks step in, "
                                     "and what reviewers decided.")
api = get_client()
try:
    s = cached_summary()
    fb = api.feedback_summary()
except ApiError as exc:
    st.error(exc.message)
    st.stop()

by_status = s.get("queries_by_status") or {}
asked = s.get("queries_total", 0)
metric_row([
    {"label": "Rated helpful", "value": fb.get("positive_rate"), "tone": "ok",
     "hint": f'{fb.get("positive", 0)} of {fb.get("total", 0)} ratings'},
    {"label": "Questions asked", "value": asked, "tone": "ink"},
    {"label": "Answered directly", "value": by_status.get("answered", 0), "tone": "ok"},
    {"label": "Held for review", "value": by_status.get("pending_review", 0), "tone": "review"},
    {"label": "Blocked by safety checks", "value": by_status.get("blocked", 0), "tone": "review"},
])
st.html('<div style="height:6px"></div>')

c1, c2, c3 = st.columns([1, 1, 1.35], gap="small")
with c1:
    with panel("outcomes", 252):
        panel_title("What happened to each question")
        if not by_status:
            empty_state("No questions yet", "Outcomes appear after the first question is asked.")
        else:
            tone = {"answered": COLORS["teal"], "pending_review": COLORS["rose"], "blocked": "#8F2341",
                    "rejected": "#9AA3B5"}
            df = pd.DataFrame([{"status": STATUS.get(k, (k, ""))[0], "key": k, "count": v} for k, v in by_status.items()])
            chart = (alt.Chart(df).mark_bar(cornerRadiusEnd=5)
                     .encode(x=alt.X("count:Q", title=None), y=alt.Y("status:N", sort="-x", title=None),
                             color=alt.Color("key:N", legend=None,
                                             scale=alt.Scale(domain=list(tone), range=list(tone.values()))),
                             tooltip=["status", "count"])
                     .properties(height=max(90, 40 * len(df))))
            st.altair_chart(chart_config(chart), use_container_width=True)
with c2:
    with panel("negative", 252):
        panel_title("Marked not helpful", "Each one goes back to the review queue")
        negatives = fb.get("recent_negative") or []
        if not negatives:
            empty_state("No complaints", "Thumbs-down ratings and their comments show up here.")
        for f in negatives:
            comment = html.escape(f.get("comment") or "No comment")
            st.html(f'<div class="ev"><div class="ev-head"><span>{html.escape(str(f["created_at"])[:16].replace("T", " "))}'
                    f'</span><span>{html.escape(f.get("user") or "anonymous")}</span></div>'
                    f'<div class="ev-body">{comment}</div></div>')
with c3:
    with panel("activity", 252):
        if not st.session_state.get("reviewer_key"):
            panel_title("Activity log")
            empty_state("Reviewer key needed", "Enter it under Reviewer access in the sidebar to see the activity log.")
        else:
            tab_log, tab_decisions = st.tabs(["Activity log", "Reviewer decisions"])
            with tab_log:
                try:
                    events = api.audit(limit=200)
                except ApiError as exc:
                    events = []
                    st.error(exc.message)
                if events:
                    df = pd.DataFrame(events)
                    df["details"] = df["details"].apply(
                        lambda d: ", ".join(f"{k}: {v}" for k, v in (d or {}).items() if v not in (None, "", [])))
                    st.dataframe(df[["created_at", "event_type", "actor", "details"]], hide_index=True,
                                 use_container_width=True, height=380,
                                 column_config={"created_at": st.column_config.DatetimeColumn("When", format="D MMM, HH:mm"),
                                                "event_type": "Event", "actor": "By", "details": "Details"})
                else:
                    st.caption("No activity yet.")
            with tab_decisions:
                try:
                    decided = api.review_history(limit=200)["items"]
                except ApiError as exc:
                    decided = []
                    st.error(exc.message)
                if decided:
                    from components.review_card import item_title

                    df = pd.DataFrame([{"when": d.get("reviewed_at"), "type": d["item_type"], "item": item_title(d),
                                        "decision": STATUS.get(d["status"], (d["status"], ""))[0],
                                        "by": d.get("reviewer"), "note": d.get("reviewer_comment")} for d in decided])
                    st.dataframe(df, hide_index=True, use_container_width=True, height=380,
                                 column_config={"when": st.column_config.DatetimeColumn("When", format="D MMM, HH:mm")})
                else:
                    st.caption("No decisions yet.")
