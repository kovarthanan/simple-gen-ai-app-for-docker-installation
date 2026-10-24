import asyncio

from app.ingestion.chunker import chunk_document
from app.ingestion.loaders import LoadedPage
from app.retrieval.graph_retriever import keyword_terms
from app.retrieval.reranker import reciprocal_rank_fusion
from app.schemas.query import ContextItem


def item(i, origin="vector"):
    return ContextItem(id=f"{origin}:{i}", origin=origin, content=f"{origin} {i}")


def test_rrf_rewards_items_ranked_high_in_multiple_lists():
    a, b, c = item(1), item(2), item(3)
    fused = reciprocal_rank_fusion({"x": [a, b, c], "y": [b, a]})
    assert [i.id for i in fused][:2] in (["vector:1", "vector:2"], ["vector:2", "vector:1"])
    assert fused[-1].id == "vector:3"


def test_rrf_interleaves_vector_and_graph():
    fused = reciprocal_rank_fusion({"vector": [item(1), item(2)], "graph": [item(1, "graph"), item(2, "graph")]})
    assert {fused[0].origin, fused[1].origin} == {"vector", "graph"}


def test_chunker_respects_size_and_keeps_pages():
    text = " ".join(f"Sentence number {i} talks about something." for i in range(200))
    chunks = chunk_document("doc-1", [LoadedPage(text, page=3)], chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 5
    assert all(len(c.text) <= 360 for c in chunks)
    assert all(c.page == 3 for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)  # stable unique ids


def test_keyword_terms_fallback():
    terms = keyword_terms("What is the relationship between Acme Corp and Alice?")
    assert "Acme Corp" in terms and "Alice" in terms


def test_hybrid_retriever_returns_both_sources(container, ingested):
    retriever = container.rag_service.retriever
    result = asyncio.run(retriever.retrieve("Where does Alice work?", top_k=3, graph_depth=1,
                                            graph_limit=10, final_top_k=6))
    origins = {c.origin for c in result.contexts}
    assert origins == {"vector", "graph"}
    assert "Alice" in result.matched_entities
    assert any(f.predicate == "WORKS_AT" for f in result.graph_facts)
    assert [c.rank for c in result.contexts] == list(range(1, len(result.contexts) + 1))


def test_hybrid_retriever_survives_a_failing_store(container, ingested):
    def broken(*args, **kwargs):
        raise RuntimeError("neo4j down")

    container.graph_store.find_entities = broken
    result = asyncio.run(container.rag_service.retriever.retrieve(
        "Where does Alice work?", top_k=3, graph_depth=1, graph_limit=10, final_top_k=6))
    assert "graph" in result.errors
    assert result.contexts and all(c.origin == "vector" for c in result.contexts)
