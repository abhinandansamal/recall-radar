# Short commands for daily work. `make check` = the same gates as CI.
.PHONY: install hooks lint format types test check audit up down

install:          ## Install all dependencies exactly as locked
	uv sync --locked

hooks:            ## Install git pre-commit hooks (once per clone)
	uv run pre-commit install

lint:
	uv run ruff check .

format:
	uv run ruff format .

types:
	uv run mypy packages/core/src packages/ingest/src packages/transform/src

test:
	uv run pytest tests/unit --cov --cov-report=term

audit:
	uv export --locked --no-hashes --no-emit-workspace --format requirements-txt | uv run pip-audit --strict -r /dev/stdin

check: lint types test   ## Run before every push
	uv run ruff format --check .

up:               ## Start dev Postgres + Redis
	docker compose -f docker-compose.dev.yml --env-file .env up -d

down:
	docker compose -f docker-compose.dev.yml down
