.PHONY: up down dev logs test lint sync

up:
	docker compose up -d

down:
	docker compose down

dev:
	cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

logs:
	docker compose logs -f backend

test:
	cd backend && uv run pytest tests/ -v

lint:
	cd backend && uv run ruff check .

sync:
	cd backend && uv sync
