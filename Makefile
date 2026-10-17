.PHONY: help setup sample accel accel-test bench migrate run-backend run-frontend test test-core test-web lint format static-check up down clean

PY ?= python3
BACKEND := backend

help:            ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ -/'

setup:           ## Install backend and frontend dependencies
	$(PY) -m pip install -r $(BACKEND)/requirements-dev.txt
	cd frontend && npm install

sample:          ## Regenerate the synthetic sample data (deterministic)
	PYTHONPATH=$(BACKEND) $(PY) data/generators/generate_sample.py

accel:           ## Build the optional C++ accelerator
	$(MAKE) -C services/cpp-accelerator

accel-test:      ## Run the C++ tests (AddressSanitizer + UBSan)
	$(MAKE) -C services/cpp-accelerator test

bench:           ## Benchmark native vs NumPy fallback
	$(MAKE) -C services/cpp-accelerator bench

migrate:         ## Apply database migrations
	cd $(BACKEND) && alembic upgrade head

run-backend:     ## Start the API on :8000 (applies migrations on startup)
	cd $(BACKEND) && uvicorn --factory app.main:create_app --reload --port 8000

run-frontend:    ## Start the web UI on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test:            ## Backend tests (pytest runs everything, including API tests)
	cd $(BACKEND) && $(PY) -m pytest

test-core:       ## ML/SQL/security tests only, using the standard library runner (no web stack needed)
	cd $(BACKEND) && $(PY) -m unittest discover -s tests -p "test_*.py"

test-web:        ## Frontend tests
	cd frontend && npm run test:lib && npm test

lint:            ## Lint everything
	cd $(BACKEND) && ruff check .
	cd frontend && npm run lint && npm run typecheck

format:          ## Auto-format Python
	cd $(BACKEND) && ruff format . && ruff check --fix .

static-check:    ## Offline undefined-name / import check
	$(PY) scripts/static_check.py backend/app

up:              ## Start the Docker Compose stack
	docker compose -f deployment/docker-compose.yml --env-file .env up --build -d

down:            ## Stop the stack (keeps volumes; add -v yourself to delete data)
	docker compose -f deployment/docker-compose.yml --env-file .env down

clean:           ## Remove build output and caches (not your data)
	rm -rf frontend/dist services/cpp-accelerator/build $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
