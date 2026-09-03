.PHONY: up down load test test-db lint typecheck

up:
	docker compose up -d
	@echo "waiting for postgres..."
	@until docker compose exec -T postgres pg_isready -U postgres -d ecommerce_agent >/dev/null 2>&1; do sleep 1; done

down:
	docker compose down

load:
	poetry run load-dataset

test:
	poetry run pytest -q

test-db:
	poetry run pytest -q -m db

lint:
	poetry run ruff check .

typecheck:
	poetry run mypy .
