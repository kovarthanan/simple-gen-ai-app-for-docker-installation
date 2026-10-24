# Hybrid RAG App (Vector DB + Knowledge Graph)

FastAPI backend + Streamlit frontend. Retrieval combines Qdrant (semantic search) and Neo4j
(knowledge graph), fuses the results and passes them to an LLM, with guardrails and
human-in-the-loop review around every step.

## Request flow
```
question -> input guardrails (injection, PII, length, blocked topics)
         -> Qdrant top-k  ┐  in parallel
         -> Neo4j n-hop   ┘
         -> RRF fusion (+ optional cross-encoder) -> LLM with numbered citations
         -> output guardrails (groundedness, citations, toxicity, PII)
         -> confidence >= threshold ? answer : human review queue
```

## Ingestion flow
```
upload -> file guards (type, size) -> PII redaction -> content guards
       -> chunk -> embed -> Qdrant
       -> LLM entity/relation extraction
            confidence >= 0.8 -> Neo4j
            0.3 - 0.8         -> human review queue
            < 0.3             -> dropped
```

## Human-in-the-loop touchpoints
1. Entities/relations approved (or edited) before they enter the knowledge graph
2. Low-confidence or guardrail-flagged answers held for a reviewer to approve, edit or reject
3. Thumbs-down feedback sends an answer back to the review queue

All thresholds live in `backend/app/guardrails/config/policies.yaml`.

## Run the backend locally
```bash
cp .env.example .env            # add ANTHROPIC_API_KEY
make dbs                        # Qdrant + Neo4j in Docker
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000/docs
```
The API starts even if Qdrant/Neo4j are down; `/health` reports what's missing.

## Run everything in Docker
```bash
cp .env.example .env && make up
```
- API docs: http://localhost:8000/docs
- UI: http://localhost:8501
- Neo4j browser: http://localhost:7474

## Tests
```bash
cd backend && pytest
```
Tests use in-memory fakes for the embedder, Qdrant, Neo4j and the LLM, so they need no
Docker, model downloads or API keys.

## API overview
| Area | Endpoints |
|---|---|
| Ingest | `POST /ingest/file`, `/ingest/files`, `/ingest/text`, `/ingest/url` |
| Query | `POST /query`, `GET /query/{id}`, `GET /query/history` |
| Documents | `GET /documents`, `GET/DELETE /documents/{id}` |
| Metadata | `GET /metadata/vector`, `/metadata/graph`, `/metadata/summary`, `/metadata/graph/subgraph` |
| Review (needs `X-API-Key`) | `GET /review/pending`, `/review/history`, `/review/stats`, `/review/audit`, `POST /review/{id}/approve`, `/edit`, `/reject` |
| Feedback | `POST /feedback`, `GET /feedback/summary`, `GET /feedback` (reviewer) |
| Health | `GET /health`, `/health/live` |
