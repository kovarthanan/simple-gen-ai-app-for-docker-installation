"""SQLAlchemy engine/session for the review queue, feedback, query and audit logs.

SQLite works out of the box for local dev; set DATABASE_URL to Postgres in Docker.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def init_db(database_url: str) -> Engine:
    """Create the engine, bind sessions and create tables (use Alembic for real migrations)."""
    global _engine
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    _engine = create_engine(database_url, **kwargs)
    SessionLocal.configure(bind=_engine)

    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(_engine)
    return _engine


def dispose_db() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not initialised; call init_db() first")
    return _engine


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db() -> bool:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
