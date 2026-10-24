"""Reviewer authentication for human-in-the-loop endpoints.

Reviewers send `X-API-Key: <REVIEWER_API_KEY>` and optionally `X-Reviewer: <name>`
so decisions are attributed in the audit log. Swap this for OAuth/JWT in production.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, status

from app.api.deps import get_settings_dep
from app.config import Settings


def require_reviewer(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_reviewer: str | None = Header(default=None, alias="X-Reviewer"),
    settings: Settings = Depends(get_settings_dep),
) -> str:
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.reviewer_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reviewer API key missing or invalid",
        )
    return (x_reviewer or "reviewer").strip()[:100]
