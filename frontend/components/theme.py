"""Global styles and small layout helpers.

Pages fit the viewport: `panel()` gives a container whose height is tied to the
window, and only that panel scrolls. On narrow screens panels flow normally.
"""
from __future__ import annotations

import streamlit as st

from config import COLORS

_FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,650;"
          "12..96,750&family=Instrument+Sans:wght@400;500;600&display=swap")

CSS = f"""
<style>
@import url('{_FONTS}');
:root {{
  --fog:{COLORS['fog']}; --paper:{COLORS['paper']}; --ink:{COLORS['ink']}; --muted:{COLORS['muted']};
  --line:{COLORS['line']}; --lapis:{COLORS['lapis']}; --saffron:{COLORS['saffron']};
  --rose:{COLORS['rose']}; --teal:{COLORS['teal']};
  --lapis-soft:#E7EDFD; --saffron-soft:#FBF0DD; --rose-soft:#FBE7ED; --teal-soft:#E0F3EE;
  --display:'Bricolage Grotesque', 'Instrument Sans', sans-serif;
}}
.stApp {{ background: var(--fog); color: var(--ink); font-family:'Instrument Sans', system-ui, sans-serif; }}
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea {{ font-family: inherit; }}
[data-testid="stHeader"] {{ background: transparent; height: 2.6rem; }}
[data-testid="stMainBlockContainer"] {{ padding: 1.1rem 1.8rem .6rem; max-width: 100%; }}
[data-testid="stSidebar"] {{ background: var(--paper); border-right: 1px solid var(--line); }}
[data-testid="stSidebarHeader"] {{ padding-bottom: .25rem; }}
footer, #MainMenu {{ visibility: hidden; }}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ font-family: var(--display); color: var(--ink); letter-spacing: -0.015em; }}
:focus-visible {{ outline: 2px solid var(--lapis) !important; outline-offset: 2px; }}

/* Page header */
.page-head {{ display:flex; align-items:flex-end; justify-content:space-between; gap:1rem; margin: 0 0 .2rem; }}
.page-head h1 {{ font-size: 1.85rem; font-weight: 750; line-height: 1.05; margin: 0; padding: 0; }}
.page-head p {{ margin: .3rem 0 0; color: var(--muted); font-size: .95rem; max-width: 70ch; }}

/* Panels: white surfaces. Viewport-height panels get their height from page CSS. */
[class*="st-key-card_"], [class*="st-key-panel_"] {{
  background: var(--paper); border: 1px solid var(--line); border-radius: 16px; padding: 14px 16px;
}}
[class*="st-key-panel_"] {{ overflow-y: auto; overflow-x: hidden; }}
.panel-title {{ font-family: var(--display); font-weight: 650; font-size: 1.05rem; margin: 0 0 .15rem; color: var(--ink); }}
.panel-sub {{ color: var(--muted); font-size: .85rem; margin: 0 0 .4rem; }}

/* Metric tiles */
.tiles {{ display:grid; grid-template-columns: repeat(var(--cols), minmax(0,1fr)); gap: 10px; }}
.tile {{ background: var(--paper); border:1px solid var(--line); border-radius: 12px; padding: 10px 14px 11px;
         border-left: 4px solid var(--line); }}
.tile-value {{ font-family: var(--display); font-weight: 750; font-size: 1.7rem; line-height: 1.1; color: var(--ink);
               font-variant-numeric: tabular-nums; }}
.tile-label {{ color: var(--muted); font-size: .82rem; }}
.tile-hint {{ color: var(--muted); font-size: .76rem; margin-top: 2px; }}
.tone-vec {{ border-left-color: var(--lapis); }} .tone-kg {{ border-left-color: var(--saffron); }}
.tone-review {{ border-left-color: var(--rose); }} .tone-ok {{ border-left-color: var(--teal); }}
.tone-ink {{ border-left-color: var(--ink); }}

/* Chips */
.chip {{ display:inline-flex; align-items:center; gap:5px; padding: 2px 9px; border-radius: 999px; font-size: .76rem;
         font-weight: 600; border: 1px solid transparent; line-height: 1.5; white-space: nowrap; margin: 0 4px 4px 0; }}
.chip .dot {{ width:7px; height:7px; border-radius:50%; background: currentColor; }}
.chip-ok {{ background: var(--teal-soft); color: var(--teal); }}
.chip-vec {{ background: var(--lapis-soft); color: var(--lapis); }}
.chip-kg {{ background: var(--saffron-soft); color: #9A5C05; }}
.chip-review {{ background: transparent; color: var(--rose); border-color: var(--rose); }}
.chip-block {{ background: var(--rose); color: #fff; }}
.chip-neutral {{ background: #EEF0F4; color: var(--muted); }}

/* Citations inside answers */
.cite {{ display:inline-block; min-width: 1.35em; padding: 0 .35em; margin: 0 1px; border-radius: 6px; text-align:center;
         font-size: .78em; font-weight: 700; line-height: 1.45; vertical-align: 1px; }}
.cite-vec {{ background: var(--lapis); color: #fff; }}
.cite-kg {{ background: var(--saffron); color: #fff; }}
.cite-none {{ background: #CBD1DC; color: var(--ink); }}

/* Evidence list */
.ev {{ border:1px solid var(--line); border-radius: 12px; padding: 9px 12px; margin-bottom: 8px; background: #FBFCFE; }}
.ev.cited {{ border-color: currentColor; }}
.ev-head {{ display:flex; justify-content:space-between; gap:8px; font-size:.8rem; color: var(--muted); margin-bottom: 3px; }}
.ev-body {{ font-size: .88rem; color: var(--ink); line-height: 1.5; }}
.ev-vec {{ color: var(--lapis); }} .ev-kg {{ color: #9A5C05; }}
.fact {{ font-weight: 600; }} .fact .pred {{ color: #9A5C05; font-weight: 700; font-size: .8rem; padding: 0 4px; }}

/* Confidence meter */
.meter {{ position:relative; height: 10px; border-radius: 999px; background: #E3E7EF; overflow: visible; margin: 6px 0 4px; }}
.meter > span {{ position:absolute; left:0; top:0; bottom:0; border-radius: 999px; }}
.meter > i {{ position:absolute; top:-4px; bottom:-4px; width:2px; background: var(--ink); opacity:.55; }}
.meter-row {{ display:flex; justify-content:space-between; font-size:.8rem; color: var(--muted); }}
.big-num {{ font-family: var(--display); font-weight: 750; font-size: 2.1rem; line-height: 1; font-variant-numeric: tabular-nums; }}

/* Pipeline steps (a real sequence, so numbered) */
.steps {{ list-style:none; margin:0 !important; padding:0 !important; counter-reset: step; }}
.steps li {{ margin: 0 !important; }}
.st-key-panel_queue .stButton button {{ justify-content: flex-start; text-align: left; }}
.st-key-panel_queue .stButton button p {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.steps li {{ counter-increment: step; display:grid; grid-template-columns: 30px 1fr; gap: 10px; padding: 5px 0;
             border-bottom: 1px dashed var(--line); }}
.steps li:last-child {{ border-bottom: 0; }}
.steps li::before {{ content: counter(step); font-family: var(--display); font-weight: 750; width: 26px; height: 26px;
                     border-radius: 8px; display:grid; place-items:center; background: #EEF0F4; color: var(--ink); font-size: .85rem; }}
.steps li.vec::before {{ background: var(--lapis); color:#fff; }} .steps li.kg::before {{ background: var(--saffron); color:#fff; }}
.steps li.review::before {{ background: var(--rose); color:#fff; }}
.steps b {{ font-weight: 600; font-size: .92rem; }}
.steps span {{ display:block; color: var(--muted); font-size: .8rem; line-height: 1.35; }}

/* Routing bar (ingest result) */
.route {{ display:flex; height: 14px; border-radius: 999px; overflow:hidden; background:#E3E7EF; margin: 6px 0; }}
.route > span {{ height:100%; }}
.legend {{ display:flex; flex-wrap:wrap; gap: 4px 14px; font-size:.8rem; color: var(--muted); }}
.legend b {{ color: var(--ink); font-variant-numeric: tabular-nums; }}
.sw {{ display:inline-block; width:9px; height:9px; border-radius:3px; margin-right:5px; vertical-align: 0; }}

/* Lists */
.row-item {{ display:flex; justify-content:space-between; align-items:center; gap:10px; padding: 7px 0;
             border-bottom: 1px solid #EEF0F4; font-size: .88rem; }}
.row-item:last-child {{ border-bottom: 0; }}
.row-item .q {{ overflow:hidden; text-overflow: ellipsis; white-space: nowrap; }}
.muted {{ color: var(--muted); }}
.empty {{ border: 1.5px dashed var(--line); border-radius: 14px; padding: 18px; text-align:center; color: var(--muted); }}
.empty b {{ display:block; color: var(--ink); font-family: var(--display); font-size: 1.05rem; margin-bottom: 4px; }}

/* Widgets */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  border-radius: 10px; font-weight: 600; }}
[data-testid="stChatMessage"] {{ background: transparent; padding: .35rem 0; }}
[data-testid="stTabs"] button p {{ font-weight: 600; }}
[data-testid="stSidebarNav"] a span {{ font-weight: 500; }}

@media (max-width: 900px) {{
  [class*="st-key-panel_"] {{ height: auto !important; max-height: none !important; }}
  .tiles {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
  [data-testid="stMainBlockContainer"] {{ padding: 1rem .9rem; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def page_header(title: str, subtitle: str | None = None, right_html: str = "") -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.html(f'<div class="page-head"><div><h1>{title}</h1>{sub}</div><div>{right_html}</div></div>')


def panel(key: str, offset_px: int):
    """A white panel that fills the viewport height minus `offset_px` and scrolls internally."""
    st.html(f"<style>.st-key-panel_{key} {{ height: calc(100vh - {offset_px}px) !important; min-height: 260px;"
            f" flex: 0 0 auto !important; box-sizing: border-box; }}</style>")
    return st.container(key=f"panel_{key}")


def card(key: str):
    """A white panel that sizes to its content."""
    return st.container(key=f"card_{key}")


def panel_title(title: str, sub: str | None = None) -> None:
    st.html(f'<div class="panel-title">{title}</div>' + (f'<div class="panel-sub">{sub}</div>' if sub else ""))


def empty_state(title: str, body: str) -> None:
    st.html(f'<div class="empty"><b>{title}</b>{body}</div>')
