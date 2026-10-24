"""Dependency wiring. All long-lived clients live in one Container on app.state.

Tests (or alternative deployments) build a Container with their own stores/LLM and
pass it to create_app(); routes only ever see the interfaces.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.core.logging import get_logger
from app.graph.base import GraphStore
from app.guardrails.base import load_policy
from app.guardrails.runner import GuardrailRunner
from app.hitl.approval_handler import ApprovalHandler
from app.hitl.notifications import Notifier
from app.hitl.policies import HITLPolicy
from app.ingestion.embedder import Embedder
from app.ingestion.entity_extractor import EntityExtractor
from app.ingestion.pipeline import IngestionPipeline
from app.llm.client import LLMClient
from app.retrieval.graph_retriever import GraphRetriever
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.reranker import Reranker
from app.retrieval.vector_retriever import VectorRetriever
from app.services.ingest_service import IngestService
from app.services.metadata_service import MetadataService
from app.services.rag_service import RAGService
from app.vectorstore.base import VectorStore

logger = get_logger(__name__)


@dataclass
class Container:
    settings: Settings
    embedder: Embedder
    vector_store: VectorStore
    graph_store: GraphStore
    llm: LLMClient
    guardrails: GuardrailRunner
    hitl_policy: HITLPolicy
    notifier: Notifier
    rag_service: RAGService
    ingest_service: IngestService
    metadata_service: MetadataService
    approval_handler: ApprovalHandler

    def startup(self) -> None:
        """Prepare stores. Failures are logged, not raised, so the API can start before the DBs."""
        try:
            self.graph_store.health()
            self.graph_store.ensure_schema()
        except Exception as exc:
            logger.warning("Knowledge graph not ready yet (%s); schema will be created on first write", exc)
        try:
            self.vector_store.health()
            self.vector_store.ensure_collection(self.embedder.dimension)  # also warms up the embedding model
        except Exception as exc:
            logger.warning("Vector store not ready yet (%s); collection will be created on first ingest", exc)

    def shutdown(self) -> None:
        for store in (self.vector_store, self.graph_store):
            try:
                store.close()
            except Exception:
                pass


def build_container(
    settings: Settings,
    *,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    graph_store: GraphStore | None = None,
    llm: LLMClient | None = None,
) -> Container:
    if embedder is None:
        from app.ingestion.embedder import SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_batch_size)
    if vector_store is None:
        from app.vectorstore.qdrant_store import QdrantVectorStore

        vector_store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_api_key, settings.qdrant_collection)
    if graph_store is None:
        from app.graph.neo4j_store import Neo4jGraphStore

        graph_store = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password,
                                      settings.neo4j_database)
    if llm is None:
        from app.llm.client import build_llm_client

        llm = build_llm_client(settings)

    policy = load_policy(settings.guardrails_policy_path)
    guardrails = GuardrailRunner(policy, embedder=embedder)
    hitl_policy = HITLPolicy(policy["hitl"], settings.hitl_confidence_threshold)
    notifier = Notifier(settings.hitl_webhook_url)
    extractor = EntityExtractor(llm, settings.entity_types, settings.max_extraction_chars)

    retriever = HybridRetriever(
        VectorRetriever(embedder, vector_store),
        GraphRetriever(graph_store, extractor if settings.use_llm_entity_linking else None),
        Reranker(settings.rrf_k, {"vector": settings.vector_weight, "graph": settings.graph_weight},
                 settings.reranker_model),
    )
    pipeline = IngestionPipeline(settings, embedder, vector_store, graph_store, extractor, guardrails, hitl_policy)

    return Container(
        settings=settings,
        embedder=embedder,
        vector_store=vector_store,
        graph_store=graph_store,
        llm=llm,
        guardrails=guardrails,
        hitl_policy=hitl_policy,
        notifier=notifier,
        rag_service=RAGService(settings, retriever, llm, guardrails, hitl_policy, notifier),
        ingest_service=IngestService(settings, pipeline, vector_store, graph_store, notifier),
        metadata_service=MetadataService(settings, vector_store, graph_store, settings.embedding_model),
        approval_handler=ApprovalHandler(graph_store),
    )


# --- FastAPI dependencies ----------------------------------------------------------
def get_container(request: Request) -> Container:
    return request.app.state.container


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.container.settings


def get_rag_service(request: Request) -> RAGService:
    return request.app.state.container.rag_service


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.container.ingest_service


def get_metadata_service(request: Request) -> MetadataService:
    return request.app.state.container.metadata_service


def get_approval_handler(request: Request) -> ApprovalHandler:
    return request.app.state.container.approval_handler


def get_hitl_policy(request: Request) -> HITLPolicy:
    return request.app.state.container.hitl_policy
