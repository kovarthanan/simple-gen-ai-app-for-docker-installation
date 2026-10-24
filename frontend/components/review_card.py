"""One review item with approve / approve-with-edits / reject actions."""
from __future__ import annotations

import html

import streamlit as st

from components.chat import answer_html
from components.guardrail_badge import chip, guard_flags_html
from components.metric_cards import meter_html
from components.sources import evidence_item_html
from config import ENTITY_TYPES
from services.api_client import ApiError, clear_cache, get_client

TYPE_NAMES = {"answer": "Answer", "entity": "Entity", "relation": "Relationship"}
TYPE_TONES = {"answer": "vec", "entity": "kg", "relation": "kg"}


def item_title(item: dict) -> str:
    p = item.get("payload") or {}
    if item["item_type"] == "answer":
        return p.get("query") or "Answer"
    if item["item_type"] == "entity":
        e = p.get("entity") or {}
        return f'{e.get("name", "?")} ({e.get("label", "Other")})'
    r = p.get("relation") or {}
    return f'{r.get("subject", "?")} {str(r.get("predicate", "")).replace("_", " ").lower()} {r.get("object", "?")}'


def _label_index(label: str | None) -> int:
    return ENTITY_TYPES.index(label) if label in ENTITY_TYPES else ENTITY_TYPES.index("Other")


def render_review_card(item: dict) -> None:
    p = item.get("payload") or {}
    kind = item["item_type"]
    st.html(
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:10px">'
        f'<div>{chip(TYPE_NAMES.get(kind, kind), TYPE_TONES.get(kind, "neutral"))}'
        f'<span class="muted" style="font-size:.82rem">{html.escape(p.get("filename") or "")}</span></div>'
        f'<div style="min-width:180px">{meter_html(item.get("confidence"), None, "Model confidence")}</div></div>'
        f'<div class="panel-title" style="font-size:1.2rem;margin-top:6px">{html.escape(item_title(item))}</div>'
        f'<div class="panel-sub">Why it\'s here: {html.escape(item.get("reason") or "")}</div>'
    )

    edits: dict | None = None
    key = item["id"]

    if kind == "answer":
        contexts = p.get("contexts") or []
        st.html('<div class="panel-sub" style="margin-top:6px">Draft answer</div>'
                f'<div class="ev">{answer_html(p.get("draft_answer") or "", contexts)}</div>')
        final = st.text_area("Answer to publish", value=p.get("draft_answer") or "", height=110, key=f"ans_{key}",
                             help="Edit the text to correct it. Keep the [n] citations that still apply.")
        if final.strip() != (p.get("draft_answer") or "").strip():
            edits = {"final_answer": final.strip()}
        if p.get("user_feedback"):
            st.html(f'<div class="panel-sub">User comment: <b style="color:var(--ink)">{html.escape(p["user_feedback"])}</b></div>')
        with st.expander(f"Evidence the model saw ({len(contexts)})"):
            st.html("".join(evidence_item_html(c) for c in contexts) or '<span class="muted">No context.</span>')
        flags = p.get("guard_flags") or []
        if flags:
            st.html('<div class="panel-sub" style="margin-top:4px">Checks</div>' + guard_flags_html(flags))

    elif kind == "entity":
        e = p.get("entity") or {}
        c1, c2 = st.columns([1.6, 1])
        name = c1.text_input("Name", value=e.get("name", ""), key=f"en_{key}")
        label = c2.selectbox("Type", ENTITY_TYPES, index=_label_index(e.get("label")), key=f"el_{key}")
        if name.strip() != e.get("name", "") or label != e.get("label"):
            edits = {"entity": {"name": name.strip(), "label": label}}
        st.caption(f"Mentioned in {len(e.get('chunk_ids') or [])} passage(s). Approving adds it to the knowledge graph.")

    elif kind == "relation":
        r = p.get("relation") or {}
        s, o = p.get("subject_entity") or {}, p.get("object_entity") or {}
        c1, c2, c3 = st.columns([1.2, 1, 1.2])
        s_name = c1.text_input("From", value=s.get("name", ""), key=f"rs_{key}")
        s_label = c1.selectbox("Type", ENTITY_TYPES, index=_label_index(s.get("label")), key=f"rsl_{key}")
        pred = c2.text_input("Relationship", value=r.get("predicate", ""), key=f"rp_{key}",
                             help="Short verb phrase, e.g. WORKS_AT")
        o_name = c3.text_input("To", value=o.get("name", ""), key=f"ro_{key}")
        o_label = c3.selectbox("Type ", ENTITY_TYPES, index=_label_index(o.get("label")), key=f"rol_{key}")
        changed = (s_name.strip() != s.get("name") or s_label != s.get("label") or pred.strip() != r.get("predicate")
                   or o_name.strip() != o.get("name") or o_label != o.get("label"))
        if changed:
            edits = {"relation": {"predicate": pred.strip()},
                     "subject_entity": {"name": s_name.strip(), "label": s_label},
                     "object_entity": {"name": o_name.strip(), "label": o_label}}
        st.caption("Approving adds both entities and this relationship to the knowledge graph.")

    comment = st.text_input("Note for the activity log (optional)", key=f"cm_{key}")
    b1, b2, _ = st.columns([1.3, 1, 1.4])
    approve_label = "Approve with edits" if edits else "Approve"
    if b1.button(approve_label, type="primary", icon=":material/check:", key=f"ok_{key}", use_container_width=True):
        _decide(lambda c: c.approve_with_edits(key, edits, comment or None) if edits else c.approve(key, comment or None),
                "Approved" + (" with edits" if edits else ""))
    if b2.button("Reject", icon=":material/close:", key=f"no_{key}", use_container_width=True):
        _decide(lambda c: c.reject(key, comment or None), "Rejected")


def _decide(action, done_message: str) -> None:
    try:
        action(get_client())
    except ApiError as exc:
        st.error(exc.message)
        return
    clear_cache()
    st.session_state.pop("review_selected", None)
    st.toast(done_message, icon=":material/task_alt:")
    st.rerun()
