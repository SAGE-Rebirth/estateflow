# EstateFlow — common tasks. Run `make` (or `make help`) to list them.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND  := backend
FRONTEND := frontend
UV       := uv --directory $(BACKEND)

.PHONY: help check-tools setup env install services services-local stop \
        dev api worker web seed seed-no-embed \
        test lint format typecheck check evals \
        docker-up docker-down clean

help: ## Show this list
	@echo "Usage: make <target>"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup ---------------------------------------------------------------------------

check-tools: ## Verify uv, node/npm and docker are installed
	@ok=1; for t in uv node npm docker; do \
		if command -v $$t >/dev/null; then printf "  ✓ %-7s %s\n" $$t "$$($$t --version 2>&1 | head -1)"; \
		else printf "  ✗ %-7s missing\n" $$t; ok=0; fi; done; \
	if [ $$ok = 0 ]; then echo "Install the missing tools (see README → Prerequisites)."; exit 1; fi

env: ## Create .env (and frontend/.env.local) from the examples if they don't exist
	@if [ -f .env ]; then echo ".env already exists — leaving it alone."; \
	else cp .env.example .env && echo "Created .env — fill in MONGO_URL, secrets and tokens."; fi
	@[ -f $(FRONTEND)/.env.local ] || cp $(FRONTEND)/.env.example $(FRONTEND)/.env.local

install: ## Install backend (uv) and frontend (npm) packages
	$(UV) sync
	cd $(FRONTEND) && npm install

setup: check-tools env install ## One-time setup: check tools, create .env, install packages
	@echo
	@echo "Setup done. Next: 'make services' then 'make dev'."

# --- Services (Docker) ---------------------------------------------------------------

services: ## Start Redis (needed by API and worker)
	docker compose up -d redis

services-local: ## Start Redis + a local Atlas-compatible MongoDB (for tests / offline dev)
	docker compose up -d redis mongo

stop: ## Stop Docker services
	docker compose stop

# --- Run -----------------------------------------------------------------------------

dev: ## Run API, worker and dashboard together (Ctrl+C stops all)
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory api & \
	$(MAKE) --no-print-directory worker & \
	$(MAKE) --no-print-directory web & \
	wait

api: ## Run the API with auto-reload on http://localhost:8000 (docs at /docs)
	$(UV) run uvicorn app.main:app --reload --port 8000

worker: ## Run the background worker (WhatsApp replies, document reading, reminders)
	$(UV) run arq app.workers.worker.WorkerSettings

web: ## Run the dashboard on http://localhost:3000
	cd $(FRONTEND) && npm run dev

seed: ## Load demo data (demo@estateflow.dev / demo12345) into the database in .env
	$(UV) run python -m app.scripts.seed

seed-no-embed: ## Load demo data without calling Hugging Face for embeddings
	$(UV) run python -m app.scripts.seed --no-embed

# --- Quality -------------------------------------------------------------------------

test: services-local ## Run backend tests (local Mongo + Redis; never touches your .env database)
	$(UV) run pytest

lint: ## Check code style and common mistakes (Ruff + ESLint)
	$(UV) run ruff check app tests evals
	$(UV) run ruff format --check app tests evals
	cd $(FRONTEND) && npm run lint

format: ## Auto-fix style issues and reformat Python code
	$(UV) run ruff check app tests evals --fix
	$(UV) run ruff format app tests evals

typecheck: ## Type-check the frontend
	cd $(FRONTEND) && npx tsc --noEmit

check: lint typecheck test ## Everything CI should run: lint, type-check, tests

evals: ## Grade the assistant on buyer scenarios (uses Hugging Face credits)
	$(UV) run python -m evals.run

# --- Docker (everything in containers) -----------------------------------------------

docker-up: ## Build and run API, worker, dashboard and Redis in containers
	docker compose --profile app up --build -d
	@echo "Dashboard: http://localhost:3000   API: http://localhost:8000/docs"

docker-down: ## Stop and remove the containers
	docker compose --profile app down

# --- Housekeeping --------------------------------------------------------------------

clean: ## Delete installed packages and build output (re-create with 'make install')
	rm -rf $(BACKEND)/.venv $(FRONTEND)/node_modules $(FRONTEND)/.next
	find $(BACKEND) -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
