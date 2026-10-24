"""Metric tiles. `tone` colour-codes the source: vec (passages), kg (graph), review, ok, ink."""
from __future__ import annotations

import html

import streamlit as st


def fmt_number(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.0%}" if value <= 1 else f"{value:,.1f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def metric_row(items: list[dict]) -> None:
    """items: [{"label": str, "value": any, "hint": str | None, "tone": str}]"""
    cells = []
    for it in items:
        hint = f'<div class="tile-hint">{html.escape(str(it["hint"]))}</div>' if it.get("hint") else ""
        cells.append(
            f'<div class="tile tone-{it.get("tone", "ink")}">'
            f'<div class="tile-label">{html.escape(it["label"])}</div>'
            f'<div class="tile-value">{html.escape(fmt_number(it.get("value")))}</div>{hint}</div>'
        )
    st.html(f'<div class="tiles" style="--cols:{len(items)}">{"".join(cells)}</div>')


def meter_html(value: float | None, threshold: float | None = None, label: str = "Confidence") -> str:
    """Horizontal meter; colour follows the value, a tick marks the review threshold."""
    if value is None:
        return f'<div class="meter-row"><span>{label}</span><span>–</span></div><div class="meter"></div>'
    v = max(0.0, min(1.0, float(value)))
    color = "var(--teal)" if threshold is None or v >= threshold else "var(--rose)"
    tick = f'<i style="left:{threshold * 100:.0f}%" title="Review threshold"></i>' if threshold is not None else ""
    return (f'<div class="meter-row"><span>{label}</span><span><b style="color:var(--ink)">{v:.0%}</b></span></div>'
            f'<div class="meter"><span style="width:{v * 100:.0f}%;background:{color}"></span>{tick}</div>')
