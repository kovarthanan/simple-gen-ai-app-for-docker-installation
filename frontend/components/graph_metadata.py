"""Knowledge graph (Neo4j) metadata panel."""
from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

from components.guardrail_badge import chip
from components.metric_cards import metric_row
from components.theme import empty_state, panel_title
from components.vector_metadata import chart_config
from config import COLORS, LABEL_PALETTE


def label_colors(labels: list[str]) -> dict[str, str]:
    return {label: LABEL_PALETTE[i % len(LABEL_PALETTE)] for i, label in enumerate(sorted(labels))}


def render_graph_metadata(meta: dict) -> None:
    panel_title("Facts in the knowledge graph", "Neo4j entities and the relationships between them")
    if not meta.get("available", True):
        st.error(f"Neo4j isn't reachable: {meta.get('error')}")
        return

    metric_row([
        {"label": "Entities", "value": meta.get("total_nodes", 0), "tone": "kg"},
        {"label": "Relationships", "value": meta.get("total_relationships", 0), "tone": "kg"},
        {"label": "Human-checked", "value": meta.get("verified_entities", 0), "tone": "ok"},
        {"label": "Without links", "value": meta.get("isolated_nodes", 0), "tone": "ink"},
    ])

    labels = meta.get("node_labels") or []
    rels = meta.get("relationship_types") or []
    if not labels and not rels:
        empty_state("The graph is empty", "Entities appear here after you add documents and approve them.")
        return

    top = meta.get("top_entities") or []
    colors = label_colors(list(dict.fromkeys([l["label"] for l in labels] + [t.get("label") or "Other" for t in top])))

    c1, c2 = st.columns(2)
    with c1:
        st.html('<div class="panel-sub" style="margin-top:8px">Entities by type</div>')
        df = pd.DataFrame(labels)
        donut = (alt.Chart(df).mark_arc(innerRadius=46, outerRadius=82, stroke="#fff", strokeWidth=2)
                 .encode(theta="count:Q",
                         color=alt.Color("label:N", title=None,
                                         scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                                         legend=alt.Legend(orient="right", labelLimit=110)),
                         tooltip=["label", "count"])
                 .properties(height=190))
        st.altair_chart(chart_config(donut), use_container_width=True)
    with c2:
        st.html('<div class="panel-sub" style="margin-top:8px">Relationship types</div>')
        if rels:
            rdf = pd.DataFrame(rels).head(10)
            rdf["name"] = rdf["type"].str.replace("_", " ").str.lower()
            bars = (alt.Chart(rdf).mark_bar(cornerRadiusEnd=4, color=COLORS["saffron"])
                    .encode(x=alt.X("count:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                            y=alt.Y("name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=140)),
                            tooltip=["type", "count"])
                    .properties(height=max(90, 26 * len(rdf))))
            st.altair_chart(chart_config(bars), use_container_width=True)

    if top:
        st.html('<div class="panel-sub" style="margin-top:4px">Most connected entities</div>' + "".join(
            f'<div class="row-item"><span><span class="sw" style="background:{colors.get(t.get("label") or "Other")}">'
            f'</span><b>{html.escape(t["entity"])}</b> <span class="muted">{html.escape(t.get("label") or "")}</span></span>'
            f'<span class="muted">{t["degree"]} link{"s" if t["degree"] != 1 else ""}</span></div>'
            for t in top))

    keys = meta.get("property_keys") or []
    if keys:
        st.html('<div class="panel-sub" style="margin-top:10px">Stored properties: '
                + "".join(chip(k, "kg") for k in keys) + "</div>")
