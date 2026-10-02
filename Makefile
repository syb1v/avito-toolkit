.PHONY: up down logs build test lint typecheck migrate revision web-dev backend-install fetch-page bump tag import-searches reset-data worker-local browser-login cookies up-dev import-skus import-profile

BROWSER ?= brave

up:
	docker compose up -d --build

up-dev:
	PLAYWRIGHT_BROWSERS_DIR="$${PLAYWRIGHT_BROWSERS_DIR:-$$HOME/.cache/ms-playwright}" \
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build worker

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

fetch-page:
	cd backend && .venv/bin/python scripts/fetch_page.py --url "$(url)" --out /tmp/avito_page.html

import-searches:
	cd backend && .venv/bin/python scripts/import_searches.py --file "$(file)"

import-skus:
	cd backend && .venv/bin/python scripts/import_our_listings.py --file "$(file)"

import-profile:
	cd backend && .venv/bin/python scripts/import_own_profile.py --url "$(url)"

browser-login:
	cd backend && .venv/bin/python scripts/browser_login.py --url "https://www.avito.ru/"

# Автоматический перенос доверенных cookies из вашего браузера (по умолчанию Brave)
# в профиль автоматизации. Браузер должен быть закрыт.
cookies:
	cd backend && .venv/bin/python scripts/import_cookies.py --from-browser $(BROWSER) --fresh

reset-data:
	docker compose exec -T postgres psql -U avito -d avito -c "truncate search_listings, listing_snapshots, listings, sellers, market_analytics_daily, product_market_matches, our_listings, alerts, jobs, llm_runs, audit_log, searches cascade;"

worker-local:
	cd backend && BROWSER_USER_DATA_DIR=.browser-profile BROWSER_HEADLESS=false \
		$$(command -v xvfb-run >/dev/null 2>&1 && echo xvfb-run -a) \
		.venv/bin/dramatiq app.workers.tasks --processes 1 --threads 2

bump:
	python3 scripts/bump_version.py --part $(part)

tag:
	@version=$$(python3 -c 'import re; print(re.search(r"__version__ = \"([^\"]+)\"", open("backend/app/__init__.py", encoding="utf-8").read()).group(1))'); \
	git tag -a "v$$version" -m "v$$version" && \
	git push origin "v$$version"
