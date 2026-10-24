"""Vector DB (Qdrant) metadata panel."""
from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

from components.guardrail_badge import chip
from components.metric_cards import metric_row
from components.theme import empty_state, panel_title
from config import COLORS


FONT = "Instrument Sans, system-ui, -apple-system, Segoe UI, sans-serif"
STATUS_NAMES = {"green": "Healthy", "yellow": "Optimizing", "grey": "Waiting", "red": "Error"}


def chart_config(chart: alt.Chart) -> alt.Chart:
    return (chart.configure(background="transparent", font=FONT)
            .configure_view(strokeWidth=0)
            .configure_axis(labelFont=FONT, titleFont=FONT, labelColor=COLORS["muted"], labelFontSize=12,
                            titleColor=COLORS["muted"], gridColor="#E8EBF1", domain=False, tickColor="#E8EBF1",
                            labelOverlap=False)
            .configure_legend(labelFont=FONT, titleFont=FONT, labelFontSize=12, labelColor=COLORS["ink"]))


def render_vector_metadata(meta: dict) -> None:
    panel_title("Passages in the vector database",
                f"Qdrant collection {html.escape(meta.get('collection', ''))}, "
                f"embedded with {html.escape(meta.get('embedding_model', ''))}")
    if not meta.get("available", True):
        st.error(f"Qdrant isn't reachable: {meta.get('error')}")
        return

    metric_row([
        {"label": "Passages stored", "value": meta.get("vectors_count", 0), "tone": "vec"},
        {"label": "Vector size", "value": meta.get("dimension"), "tone": "vec"},
        {"label": "Similarity", "value": (meta.get("distance") or "–").capitalize(), "tone": "vec"},
        {"label": "Status", "value": STATUS_NAMES.get(meta.get("status") or "", meta.get("status") or "")
         or ("Ready" if meta.get("exists") else "Not created"), "tone": "vec"},
    ])
    fields = meta.get("payload_fields") or []
    st.html('<div style="margin:8px 0 2px" class="panel-sub">Indexed fields: '
            + ("".join(chip(f, "vec") for f in fields) if fields else "none yet") + "</div>")

    docs = meta.get("documents") or []
    if not docs:
        empty_state("No documents yet", "Add a document to see how it's split into passages.")
        return
    df = pd.DataFrame(docs)
    # documents can share a filename, so label bars by name plus a short id when needed
    dupes = df["filename"].duplicated(keep=False)
    df["doc"] = df["filename"].where(~dupes, df["filename"] + " (" + df["doc_id"].str[:4] + ")")
    top = df.sort_values("num_chunks", ascending=False).head(12)
    st.html('<div class="panel-sub" style="margin-top:6px">Passages per document</div>')
    bars = (alt.Chart(top).mark_bar(cornerRadiusEnd=4, color=COLORS["lapis"])
            .encode(x=alt.X("num_chunks:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("doc:N", sort="-x", title=None, axis=alt.Axis(labelLimit=190)),
                    tooltip=[alt.Tooltip("filename", title="Document"), alt.Tooltip("num_chunks", title="Passages")])
            .properties(height=max(90, 28 * len(top))))
    st.altair_chart(chart_config(bars), use_container_width=True)

    df["status"] = df["status"].map({"indexed": "Indexed", "indexed_pending_review": "Indexed, items to review",
                                     "failed": "Failed", "blocked": "Blocked", "processing": "Processing"}).fillna(df["status"])
    table = df[["filename", "status", "num_chunks", "num_entities", "num_relations", "pending_review", "created_at"]]
    st.dataframe(
        table, hide_index=True, use_container_width=True,
        column_config={
            "filename": "Document", "status": "Status", "num_chunks": "Passages",
            "num_entities": "Entities", "num_relations": "Relations", "pending_review": "To review",
            "created_at": st.column_config.DatetimeColumn("Added", format="D MMM, HH:mm"),
        },
    )
