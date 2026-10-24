"""Add documents: upload / paste / URL on the left, the document registry on the right."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from components.guardrail_badge import STATUS, guard_flags_html, status_chip
from components.theme import empty_state, page_header, panel, panel_title
from services.api_client import ApiError, clear_cache, get_client

FILE_TYPES = ["pdf", "docx", "txt", "md", "csv", "json", "html", "htm"]
st.session_state.setdefault("ingest_results", [])
st.session_state.setdefault("uploader_key", 0)


def parse_tags(raw: str) -> dict:
    """'team=legal, 2026, contracts' -> {"team": "legal", "tags": ["2026", "contracts"]}"""
    meta: dict = {}
    tags = []
    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            meta[k.strip()] = v.strip()
        else:
            tags.append(part)
    if tags:
        meta["tags"] = tags
    return meta


def run(label: str, fn) -> None:
    try:
        result = fn()
        st.session_state.ingest_results.insert(0, {"ok": True, **result})
        st.toast(f"Added {result['filename']}", icon=":material/task_alt:")
    except ApiError as exc:
        st.session_state.ingest_results.insert(0, {"ok": False, "filename": label, "error": exc.message})
    clear_cache()


def result_html(r: dict) -> str:
    name = html.escape(r.get("filename", ""))
    if not r.get("ok"):
        return (f'<div class="ev" style="border-color:var(--rose)"><div class="ev-head"><span><b style="color:var(--ink)">'
                f'{name}</b></span>{status_chip("failed")}</div><div class="ev-body">{html.escape(r["error"])}</div></div>')
    auto, review, dropped = r["auto_approved"], r["pending_review"], r["dropped"]
    total = max(1, auto + review + dropped)
    bar = (f'<div class="route"><span style="width:{auto / total * 100:.1f}%;background:var(--teal)"></span>'
           f'<span style="width:{review / total * 100:.1f}%;background:var(--rose)"></span>'
           f'<span style="width:{dropped / total * 100:.1f}%;background:#B9C0CD"></span></div>')
    legend = (f'<div class="legend"><span><span class="sw" style="background:var(--lapis)"></span><b>{r["num_chunks"]}</b> passages</span>'
              f'<span><span class="sw" style="background:var(--teal)"></span><b>{auto}</b> added to graph</span>'
              f'<span><span class="sw" style="background:var(--rose)"></span><b>{review}</b> waiting for review</span>'
              f'<span><span class="sw" style="background:#B9C0CD"></span><b>{dropped}</b> too uncertain, skipped</span></div>')
    pii = '<div class="panel-sub" style="margin:6px 0 0">Personal data was removed before indexing.</div>' if r.get("pii_redacted") else ""
    warnings = "".join(f'<div class="panel-sub" style="color:var(--rose);margin:4px 0 0">{html.escape(w)}</div>'
                       for w in r.get("warnings") or [])
    flags = [f for f in r.get("guard_flags") or [] if not f.get("passed") or f.get("action") == "redact"]
    flag_html = f'<div style="margin-top:6px">{guard_flags_html(flags)}</div>' if flags else ""
    return (f'<div class="ev"><div class="ev-head"><span><b style="color:var(--ink);font-size:.92rem">{name}</b></span>'
            f'{status_chip(r["status"])}</div>{bar}{legend}{pii}{warnings}{flag_html}</div>')


page_header("Add documents", "Each document is split into passages for search, and the people, places and things "
                             "in it go to the knowledge graph. Personal data is removed first.")
left, right = st.columns([1, 1.3], gap="medium")

with left:
    with panel("add", 150):
        tab_file, tab_text, tab_url = st.tabs(["Upload files", "Paste text", "From a web page"])
        with tab_file:
            files = st.file_uploader("PDF, Word, text, Markdown, CSV, JSON or HTML", type=FILE_TYPES,
                                     accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")
        with tab_text:
            title = st.text_input("Title", value="notes.txt")
            text = st.text_area("Text", height=130, placeholder="Paste meeting notes, an article, a policy...")
        with tab_url:
            url = st.text_input("Web page or PDF link", placeholder="https://example.com/report.pdf")
        tags = st.text_input("Tags (optional)", placeholder="team=legal, contracts",
                             help="Stored with every passage. Use key=value or plain words, separated by commas.")
        meta = parse_tags(tags)

        if st.button("Add to knowledge base", type="primary", icon=":material/add:", use_container_width=True):
            api = get_client()
            todo = 0
            with st.spinner("Reading, checking and indexing"):
                for f in files or []:
                    run(f.name, lambda f=f: api.ingest_file(f.name, f.getvalue(), f.type, meta))
                    todo += 1
                if text.strip():
                    run(title, lambda: api.ingest_text(text, title or "notes.txt", meta))
                    todo += 1
                if url.strip():
                    run(url, lambda: api.ingest_url(url.strip(), meta))
                    todo += 1
            if not todo:
                st.warning("Choose a file, paste some text or enter a link first.")
            else:
                st.session_state.uploader_key += 1
                st.rerun()

        if st.session_state.ingest_results:
            st.html('<div class="panel-title" style="margin-top:10px">Just added</div>'
                    + "".join(result_html(r) for r in st.session_state.ingest_results[:6]))

with right:
    with panel("docs", 150):
        try:
            docs = get_client().documents()
        except ApiError as exc:
            st.error(exc.message)
            docs = {"total": 0, "items": []}
        panel_title("Your documents", f"{docs['total']} in the knowledge base")
        if not docs["items"]:
            empty_state("Nothing here yet", "Upload a file, paste text or add a link to get started.")
        else:
            df = pd.DataFrame(docs["items"])
            df["status"] = df["status"].map(lambda s: STATUS.get(s, (s, ""))[0])
            view = df[["filename", "status", "num_chunks", "num_entities", "num_relations", "pending_review", "created_at"]]
            event = st.dataframe(
                view, hide_index=True, use_container_width=True, height=330, on_select="rerun",
                selection_mode="single-row", key="doc_table",
                column_config={
                    "filename": st.column_config.TextColumn("Document", width="medium"),
                    "status": st.column_config.TextColumn("Status", width="medium"),
                    "num_chunks": st.column_config.NumberColumn("Passages", width="small"),
                    "num_entities": st.column_config.NumberColumn("Entities", width="small"),
                    "num_relations": st.column_config.NumberColumn("Relations", width="small"),
                    "pending_review": st.column_config.NumberColumn("To review", width="small"),
                    "created_at": st.column_config.DatetimeColumn("Added", format="D MMM, HH:mm"),
                },
            )
            rows = event.selection.rows if event and event.selection else []
            if not rows:
                st.caption("Select a row to see details or delete a document.")
            else:
                doc = docs["items"][rows[0]]
                warn = "".join(f"<li>{html.escape(w)}</li>" for w in doc.get("warnings") or [])
                tags_html = html.escape(", ".join(f"{k}={v}" for k, v in (doc.get("metadata") or {}).items())) or "none"
                st.html(f'<div class="ev"><div class="ev-head"><span><b style="color:var(--ink);font-size:.95rem">'
                        f'{html.escape(doc["filename"])}</b></span>{status_chip(doc["status"])}</div>'
                        f'<div class="ev-body">{doc["num_pages"]} page(s), {doc["size_bytes"] / 1024:,.0f} KB, '
                        f'tags: {tags_html}'
                        f'{"<br>Personal data removed." if doc.get("pii_redacted") else ""}'
                        f'{f"<ul>{warn}</ul>" if warn else ""}</div></div>')
                confirm = st.checkbox("Also remove its passages and graph facts", key=f"del_ok_{doc['id']}")
                if st.button("Delete document", icon=":material/delete:", disabled=not confirm):
                    try:
                        res = get_client().delete_document(doc["id"])
                        clear_cache()
                        st.toast(f"Deleted {doc['filename']}", icon=":material/delete:")
                        for w in res.get("warnings") or []:
                            st.warning(w)
                        st.rerun()
                    except ApiError as exc:
                        st.error(exc.message)
