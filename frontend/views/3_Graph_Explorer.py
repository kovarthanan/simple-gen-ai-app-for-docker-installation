"""Knowledge graph explorer."""
from __future__ import annotations

import html
from collections import Counter

import streamlit as st

from components.graph_metadata import label_colors
from components.graph_view import render_graph
from components.theme import page_header, panel, panel_title
from services.api_client import ApiError, get_client

page_header("Knowledge graph", "Entities and relationships taken from your documents. "
                               "Click a node to see everything it's connected to.")

c1, c2, c3 = st.columns([2.2, 1.4, 0.6], vertical_alignment="bottom")
entity = c1.text_input("Focus on an entity", placeholder="Type a name, e.g. Acme Corp")
limit = c2.select_slider("Relationships to show", options=[50, 100, 200, 400, 800], value=200)
c3.button("Refresh", icon=":material/refresh:", use_container_width=True)

api = get_client()
try:
    sub = api.subgraph(limit=limit, entity=entity.strip() or None)
    meta = api.graph_metadata(top_n=5)
except ApiError as exc:
    st.error(exc.message)
    st.stop()

all_labels = [l["label"] for l in meta.get("node_labels") or []] + [n.get("label") or "Other" for n in sub["nodes"]]
colors = label_colors(list(dict.fromkeys(all_labels)))

st.html("<style>.st-key-graphwrap iframe { height: calc(100vh - 232px) !important; min-height: 300px;"
        " border: 1px solid var(--line); border-radius: 16px; }</style>")
left, right = st.columns([3.3, 1], gap="small")
with left:
    with st.container(key="graphwrap"):
        render_graph(sub, colors, height=300)  # real height comes from the CSS above
with right:
    with panel("legend", 232):
        panel_title("In view", f"{len(sub['nodes'])} entities, {len(sub['edges'])} relationships"
                    + (f" around {html.escape(entity)}" if entity.strip() else ""))
        counts = Counter(n.get("label") or "Other" for n in sub["nodes"])
        st.html('<div class="panel-sub" style="margin-top:8px">Entity types</div>' + "".join(
            f'<div class="row-item"><span><span class="sw" style="background:{colors.get(lbl, "#4B5A73")}"></span>'
            f'{html.escape(lbl)}</span><b>{n}</b></div>' for lbl, n in counts.most_common()) if counts else "")
        preds = Counter(e["type"] for e in sub["edges"])
        if preds:
            st.html('<div class="panel-sub" style="margin-top:12px">Relationship types</div>' + "".join(
                f'<div class="row-item"><span style="color:#9A5C05;font-weight:600">'
                f'{html.escape(p.replace("_", " ").lower())}</span><b>{n}</b></div>' for p, n in preds.most_common(12)))
        top = meta.get("top_entities") or []
        if top and not entity.strip():
            st.html('<div class="panel-sub" style="margin-top:12px">Most connected overall</div>' + "".join(
                f'<div class="row-item"><span>{html.escape(t["entity"])}</span><span class="muted">{t["degree"]}</span></div>'
                for t in top))
