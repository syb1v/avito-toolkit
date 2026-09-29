.PHONY: up down logs build test lint typecheck migrate revision web-dev backend-install

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

build:
	docker compose build

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

test:
	cd backend && .venv/bin/pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests

typecheck:
	cd backend && .venv/bin/mypy app

web-dev:
	cd frontend && npm run dev
