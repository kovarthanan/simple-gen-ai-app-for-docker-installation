import io

from tests.conftest import SAMPLE_TEXT


def test_ingest_text_indexes_vectors_and_routes_entities(client, container, ingested):
    assert ingested["status"] == "indexed_pending_review"
    assert ingested["num_chunks"] >= 1
    assert ingested["entities_extracted"] == 4
    assert ingested["auto_approved"] == 3      # Alice, Acme Corp, WORKS_AT
    assert ingested["pending_review"] == 2     # Chennai + LOCATED_IN
    assert ingested["dropped"] == 1            # Blob
    assert ingested["pii_redacted"] is True

    graph = container.graph_store
    assert "alice" in graph.entities and "chennai" not in graph.entities
    assert ("alice", "WORKS_AT", "acme corp") in graph.relations


def test_pii_is_redacted_before_embedding(container, ingested):
    texts = [r.payload["text"] for r in container.vector_store.records.values()]
    assert all("alice@example.com" not in t for t in texts)
    assert any("[REDACTED_EMAIL]" in t for t in texts)


def test_file_upload_and_document_registry(client):
    r = client.post("/ingest/file", files={"file": ("acme.txt", io.BytesIO(SAMPLE_TEXT.encode()), "text/plain")},
                    data={"metadata": '{"team": "sales"}'})
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc_id"]

    docs = client.get("/documents").json()
    assert docs["total"] == 1 and docs["items"][0]["metadata"] == {"team": "sales"}
    assert client.get(f"/documents/{doc_id}").json()["filename"] == "acme.txt"


def test_blocked_file_type(client):
    r = client.post("/ingest/file", files={"file": ("run.exe", io.BytesIO(b"MZ..."), "application/octet-stream")})
    assert r.status_code == 422
    assert r.json()["error"] == "guardrail_violation"


def test_too_little_text_is_blocked(client):
    r = client.post("/ingest/text", json={"text": "hi", "title": "tiny.txt"})
    assert r.status_code == 422
    assert client.get("/documents").json()["items"][0]["status"] == "blocked"


def test_delete_document_cleans_everything(client, container, ingested):
    doc_id = ingested["doc_id"]
    r = client.delete(f"/documents/{doc_id}")
    assert r.status_code == 200 and r.json()["reviews_removed"] == 2
    assert not container.vector_store.records
    assert not container.graph_store.relations
    assert client.get(f"/documents/{doc_id}").status_code == 404


def test_extraction_failure_still_indexes_vectors(client, container, fakes):
    fakes["llm"].extraction = None  # -> json "null" -> no dict -> extraction warning
    def broken(*a, **k):
        raise RuntimeError("LLM down")
    fakes["llm"].complete = broken
    r = client.post("/ingest/text", json={"text": SAMPLE_TEXT, "title": "acme.txt"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "indexed" and body["num_chunks"] >= 1
    assert any("extraction failed" in w for w in body["warnings"])
