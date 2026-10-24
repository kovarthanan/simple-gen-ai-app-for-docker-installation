"""Liveness / readiness checks for the API and its dependencies."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.db.session import check_db

router = APIRouter(tags=["health"])


async def _check(fn) -> str:
    try:
        ok = await asyncio.wait_for(asyncio.to_thread(fn), timeout=8)
        return "ok" if ok else "down"
    except Exception as exc:
        return f"down: {type(exc).__name__}"


@router.get("/health")
async def health(container: Container = Depends(get_container)) -> dict:
    checks = {
        "api": "ok",
        "database": await _check(check_db),
        "vector_store": await _check(container.vector_store.health),
        "graph_store": await _check(container.graph_store.health),
        "llm": "configured" if container.llm.is_configured() else "not configured (missing API key)",
    }
    healthy = all(v in ("ok", "configured") for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}
