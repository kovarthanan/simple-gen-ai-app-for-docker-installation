"""Thin client for the FastAPI backend. Every call raises ApiError with a readable message."""
from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

from config import BACKEND_URL, REQUEST_TIMEOUT, REVIEWER_API_KEY


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300] or f"HTTP {resp.status_code}"
    if isinstance(body, dict):
        if body.get("message"):
            return body["message"]
        detail = body.get("detail")
        if isinstance(detail, list):  # FastAPI validation errors
            return "; ".join(f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}" for d in detail)
        if detail:
            return str(detail)
    return f"HTTP {resp.status_code}"


class ApiClient:
    def __init__(self, base_url: str, timeout: float, reviewer_key: str = "", reviewer_name: str = ""):
        self.base_url = base_url
        self.timeout = timeout
        self.reviewer_key = reviewer_key
        self.reviewer_name = reviewer_name

    def _request(self, method: str, path: str, *, reviewer: bool = False, timeout: float | None = None,
                 **kwargs: Any) -> Any:
        timeout = timeout or self.timeout
        headers = kwargs.pop("headers", {})
        if reviewer:
            if not self.reviewer_key:
                raise ApiError(401, "Enter the reviewer key in the sidebar to use the review tools.")
            headers["X-API-Key"] = self.reviewer_key
            if self.reviewer_name:
                headers["X-Reviewer"] = self.reviewer_name
        try:
            resp = httpx.request(method, f"{self.base_url}{path}", headers=headers,
                                 timeout=timeout, **kwargs)
        except httpx.ConnectError:
            raise ApiError(0, f"Can't reach the backend at {self.base_url}. Start it with "
                              "`uvicorn app.main:app --reload` in the backend folder.") from None
        except httpx.TimeoutException:
            raise ApiError(0, f"The backend took longer than {timeout:.0f}s to respond. Check that Qdrant "
                              "and Neo4j are running (`docker compose up -d qdrant neo4j`).") from None
        if resp.status_code == 401 and reviewer:
            raise ApiError(401, "The reviewer key was not accepted. Check REVIEWER_API_KEY in the backend .env.")
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, _error_message(resp))
        return resp.json() if resp.content else None

    # -- health & metadata --------------------------------------------------------
    # Called on every page (sidebar status, nav badge), so they get a short timeout
    def health(self) -> dict:
        return self._request("GET", "/health", timeout=10)

    def summary(self) -> dict:
        return self._request("GET", "/metadata/summary", timeout=10)

    def vector_metadata(self) -> dict:
        return self._request("GET", "/metadata/vector")

    def graph_metadata(self, top_n: int = 10) -> dict:
        return self._request("GET", "/metadata/graph", params={"top_n": top_n})

    def subgraph(self, limit: int = 150, entity: str | None = None) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if entity:
            params["entity"] = entity
        return self._request("GET", "/metadata/graph/subgraph", params=params)

    # -- ingestion ---------------------------------------------------------------------
    def ingest_file(self, name: str, data: bytes, mime: str | None, metadata: dict | None = None) -> dict:
        form = {"metadata": json.dumps(metadata)} if metadata else {}
        return self._request("POST", "/ingest/file", files={"file": (name, data, mime or "application/octet-stream")},
                             data=form)

    def ingest_text(self, text: str, title: str, metadata: dict | None = None) -> dict:
        return self._request("POST", "/ingest/text", json={"text": text, "title": title, "metadata": metadata or {}})

    def ingest_url(self, url: str, metadata: dict | None = None) -> dict:
        return self._request("POST", "/ingest/url", json={"url": url, "metadata": metadata or {}})

    def documents(self, limit: int = 200) -> dict:
        return self._request("GET", "/documents", params={"limit": limit})

    def delete_document(self, doc_id: str) -> dict:
        return self._request("DELETE", f"/documents/{doc_id}")

    # -- questions ------------------------------------------------------------------------
    def query(self, payload: dict) -> dict:
        return self._request("POST", "/query", json=payload)

    def get_query(self, query_id: str) -> dict:
        return self._request("GET", f"/query/{query_id}")

    def history(self, limit: int = 20, status: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self._request("GET", "/query/history", params=params)

    # -- feedback ---------------------------------------------------------------------------
    def send_feedback(self, query_id: str, rating: int, comment: str | None = None) -> dict:
        return self._request("POST", "/feedback", json={"query_id": query_id, "rating": rating, "comment": comment})

    def feedback_summary(self) -> dict:
        return self._request("GET", "/feedback/summary")

    # -- review (reviewer key required) -----------------------------------------------------
    def review_pending(self, item_type: str | None = None, limit: int = 100) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if item_type:
            params["item_type"] = item_type
        return self._request("GET", "/review/pending", reviewer=True, params=params)

    def review_history(self, limit: int = 100) -> dict:
        return self._request("GET", "/review/history", reviewer=True, params={"limit": limit})

    def review_stats(self) -> dict:
        return self._request("GET", "/review/stats", reviewer=True)

    def approve(self, item_id: str, comment: str | None = None) -> dict:
        return self._request("POST", f"/review/{item_id}/approve", reviewer=True, json={"comment": comment})

    def approve_with_edits(self, item_id: str, payload: dict, comment: str | None = None) -> dict:
        return self._request("POST", f"/review/{item_id}/edit", reviewer=True,
                             json={"payload": payload, "comment": comment})

    def reject(self, item_id: str, comment: str | None = None) -> dict:
        return self._request("POST", f"/review/{item_id}/reject", reviewer=True, json={"comment": comment})

    def audit(self, limit: int = 200) -> list[dict]:
        return self._request("GET", "/review/audit", reviewer=True, params={"limit": limit})


def get_client() -> ApiClient:
    return ApiClient(
        BACKEND_URL,
        REQUEST_TIMEOUT,
        reviewer_key=st.session_state.get("reviewer_key") or REVIEWER_API_KEY,
        reviewer_name=st.session_state.get("reviewer_name", ""),
    )


# Cached reads for dashboards (cleared after any change)
@st.cache_data(ttl=15, show_spinner=False)
def cached_summary(_base: str = BACKEND_URL) -> dict:
    return get_client().summary()


@st.cache_data(ttl=10, show_spinner=False)
def cached_health(_base: str = BACKEND_URL) -> dict:
    return get_client().health()


def clear_cache() -> None:
    st.cache_data.clear()
