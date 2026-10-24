from tests.conftest import REVIEWER


def test_review_endpoints_require_reviewer_key(client):
    assert client.get("/review/pending").status_code == 401
    assert client.get("/review/pending", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/review/pending", headers=REVIEWER).status_code == 200


def test_approving_entity_and_relation_writes_them_to_graph(client, container, ingested):
    pending = client.get("/review/pending", headers=REVIEWER).json()
    assert pending["total"] == 2
    by_type = {i["item_type"]: i for i in pending["items"]}

    r = client.post(f"/review/{by_type['entity']['id']}/approve", headers=REVIEWER, json={"comment": "correct"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert container.graph_store.entities["chennai"]["verified"] is True

    r = client.post(f"/review/{by_type['relation']['id']}/approve", headers=REVIEWER)
    assert r.status_code == 200
    assert ("acme corp", "LOCATED_IN", "chennai") in container.graph_store.relations

    doc = client.get(f"/documents/{ingested['doc_id']}").json()
    assert doc["pending_review"] == 0 and doc["status"] == "indexed"

    # can't decide twice
    assert client.post(f"/review/{by_type['entity']['id']}/reject", headers=REVIEWER).status_code == 409


def test_edit_entity_before_approving(client, container, ingested):
    item = client.get("/review/pending?item_type=entity", headers=REVIEWER).json()["items"][0]
    r = client.post(f"/review/{item['id']}/edit", headers=REVIEWER,
                    json={"payload": {"entity": {"name": "Chennai, India", "label": "Location"}}})
    assert r.status_code == 200 and r.json()["status"] == "edited"
    assert "chennai, india" in container.graph_store.entities


def test_reject_relation_keeps_graph_clean(client, container, ingested):
    item = client.get("/review/pending?item_type=relation", headers=REVIEWER).json()["items"][0]
    assert client.post(f"/review/{item['id']}/reject", headers=REVIEWER,
                       json={"comment": "wrong office"}).json()["status"] == "rejected"
    assert ("acme corp", "LOCATED_IN", "chennai") not in container.graph_store.relations


def test_answer_review_edit_publishes_final_answer(client, fakes, ingested):
    fakes["llm"].answer_override = "The moon is made of green cheese and orbits Jupiter every week."
    query = client.post("/query", json={"query": "Where does Alice work?"}).json()
    assert query["status"] == "pending_review"

    r = client.post(f"/review/{query['review_id']}/edit", headers=REVIEWER,
                    json={"payload": {"final_answer": "Alice works at Acme Corp in Chennai. [1]"},
                          "comment": "fixed hallucination"})
    assert r.status_code == 200

    result = client.get(f"/query/{query['query_id']}").json()
    assert result["status"] == "answered" and result["reviewed"] is True
    assert result["answer"] == "Alice works at Acme Corp in Chennai. [1]"

    audit = client.get("/review/audit?event_type=review", headers=REVIEWER).json()
    assert audit[0]["event_type"] == "review.edited" and audit[0]["actor"] == "alice-reviewer"


def test_rejected_answer(client, fakes, ingested):
    fakes["llm"].answer_override = "The moon is made of green cheese and orbits Jupiter every week."
    query = client.post("/query", json={"query": "Where does Alice work?"}).json()
    client.post(f"/review/{query['review_id']}/reject", headers=REVIEWER, json={"comment": "hallucinated"})
    result = client.get(f"/query/{query['query_id']}").json()
    assert result["status"] == "rejected" and result["answer"] is None


def test_negative_feedback_sends_answer_to_review(client, ingested):
    query = client.post("/query", json={"query": "Where does Alice work?"}).json()
    assert query["status"] == "answered"

    up = client.post("/feedback", json={"query_id": query["query_id"], "rating": 1})
    assert up.status_code == 201 and up.json()["sent_to_review"] is False

    down = client.post("/feedback", json={"query_id": query["query_id"], "rating": -1, "comment": "too short"})
    assert down.json()["sent_to_review"] is True
    answers = client.get("/review/pending?item_type=answer", headers=REVIEWER).json()
    assert answers["total"] == 1 and "too short" in answers["items"][0]["reason"]

    summary = client.get("/feedback/summary").json()
    assert summary["total"] == 2 and summary["positive_rate"] == 0.5
    assert summary["recent_negative"][0]["comment"] == "too short"


def test_feedback_for_unknown_query(client):
    assert client.post("/feedback", json={"query_id": "nope", "rating": 1}).status_code == 404


def test_review_stats(client, ingested):
    stats = client.get("/review/stats", headers=REVIEWER).json()
    assert stats["pending"] == 2 and stats["pending_by_type"] == {"entity": 1, "relation": 1}
