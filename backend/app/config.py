"""Application settings, loaded from environment variables / .env files."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),  # repo-root .env when run from backend/, or a local one
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App -------------------------------------------------------------
    app_name: str = "Hybrid RAG API"
    app_version: str = "0.1.0"
    environment: str = "dev"
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

    # --- LLM -------------------------------------------------------------
    llm_provider: str = "anthropic"  # anthropic | openai | ollama
    llm_model: str = "claude-sonnet-5-5"
    llm_max_tokens: int = 1024
    llm_temperature: float | None = None  # None = provider default
    llm_timeout_seconds: float = 60.0
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"  # any OpenAI-compatible API works
    ollama_base_url: str = "http://localhost:11434"

    # --- Embeddings / reranking -------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    reranker_model: str | None = None  # e.g. "cross-encoder/ms-marco-MiniLM-L-6-v2"; None = RRF only

    # --- Vector DB (Qdrant) ------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "documents"

    # --- Knowledge graph (Neo4j) -------------------------------------------
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str | None = None

    # --- Relational DB (review queue, feedback, audit log) -----------------
    database_url: str = "sqlite:///./rag_hitl.db"

    # --- Ingestion -----------------------------------------------------------
    upload_dir: str = "../data/raw"
    chunk_size: int = 800
    chunk_overlap: int = 120
    entity_types: list[str] = [
        "Person", "Organization", "Location", "Product", "Technology",
        "Concept", "Event", "Date", "Document", "Other",
    ]
    max_extraction_chars: int = 6000  # text sent to the LLM per extraction call
    allow_private_urls: bool = False  # SSRF protection for /ingest/url

    # --- Retrieval -----------------------------------------------------------
    vector_top_k: int = 5
    graph_depth: int = 1
    graph_limit: int = 25
    final_top_k: int = 8
    rrf_k: int = 60
    vector_weight: float = 1.0
    graph_weight: float = 1.0
    use_llm_entity_linking: bool = True  # use the LLM to find entities in the question

    # --- Guardrails & human-in-the-loop -------------------------------------
    guardrails_policy_path: str = "app/guardrails/config/policies.yaml"
    hitl_confidence_threshold: float | None = None  # overrides policies.yaml when set
    reviewer_api_key: str = "change-me"
    hitl_webhook_url: str | None = None  # Slack-compatible webhook for reviewer notifications


@lru_cache
def get_settings() -> Settings:
    return Settings()
