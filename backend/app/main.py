"""FastAPI entrypoint.

Run locally:  uvicorn app.main:app --reload   (from the backend/ folder)
API docs:     http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Container, build_container
from app.api.routes import documents, feedback, health, ingest, metadata, query, review
from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db.session import dispose_db, init_db

logger = get_logger(__name__)


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = container.settings if container else (settings or get_settings())
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "container", None) is None:
            app.state.container = build_container(settings)
        init_db(settings.database_url)
        app.state.container.startup()
        logger.info("%s started (LLM: %s/%s)", settings.app_name, settings.llm_provider, settings.llm_model)
        yield
        app.state.container.shutdown()
        dispose_db()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Hybrid RAG over a vector DB (Qdrant) and a knowledge graph (Neo4j), "
                    "with guardrails and human-in-the-loop review.",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    for router in (health.router, ingest.router, query.router, documents.router,
                   metadata.router, review.router, feedback.router):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs"}

    return app


app = create_app()
