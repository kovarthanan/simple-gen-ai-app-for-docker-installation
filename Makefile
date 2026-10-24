up:
	docker compose up --build

down:
	docker compose down

dbs:
	docker compose up -d qdrant neo4j

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

test:
	cd backend && pytest

seed:
	python scripts/seed_data.py
