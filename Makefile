# Field Technician Assistant — every agent and human uses these same entry points.
SHELL := /bin/bash
UV ?= uv
NPM ?= npm
PORT ?= 8000

.PHONY: help setup build-ui run dev test e2e typecheck check secrets smoke up down logs reset-db lock hooks context board

help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## install backend (uv) + frontend (npm ci) deps
	cd backend && $(UV) sync
	cd frontend && $(NPM) ci --no-audit --no-fund

build-ui: ## build the React UI into frontend/dist
	cd frontend && $(NPM) run build

run: build-ui ## run API + built UI locally on :8000 (no Docker)
	cd backend && $(UV) run uvicorn --factory app.main:app_factory --host 127.0.0.1 --port $(PORT)

dev: ## backend with reload + Vite dev server (:5173, proxies /api)
	(cd backend && $(UV) run uvicorn --factory app.main:app_factory --reload --port $(PORT)) & \
	(cd frontend && $(NPM) run dev); wait

test: ## backend unit + scenario + API + adapter tests + agentctl tests (no key needed)
	cd backend && $(UV) run pytest -q -p no:cacheprovider
	cd backend && $(UV) run pytest ../tools/tests -q -p no:cacheprovider --rootdir=..

e2e: build-ui ## browser tests (Playwright; set PLAYWRIGHT_CHROMIUM_EXECUTABLE or run `uv run playwright install chromium`)
	cd backend && $(UV) run pytest ../e2e -q -p no:cacheprovider --rootdir=..

typecheck: ## TypeScript typecheck
	cd frontend && $(NPM) run typecheck

secrets: ## scan tracked files for secrets / forbidden files
	python3 tools/scan_secrets.py

check: test typecheck secrets ## everything an agent must run before handing off
	python3 tools/agentctl.py doctor

smoke: ## live LLM smoke test using .env provider (prints PASS/FAIL only)
	cd backend && $(UV) run python scripts/smoke.py

up: ## one-command launch (Docker)
	docker compose up --build

down: ## stop containers (keeps data)
	docker compose down

logs:
	docker compose logs -f app

reset-db: ## DESTRUCTIVE: delete local + Docker databases (reseeds on next start)
	rm -f data/assistant.sqlite3 data/assistant.sqlite3-wal data/assistant.sqlite3-shm
	-docker compose down -v

lock: ## refresh lockfiles (uv.lock, requirements.lock, package-lock.json)
	cd backend && $(UV) lock && $(UV) export --no-dev --format requirements-txt --no-emit-project -o requirements.lock
	cd frontend && $(NPM) install --package-lock-only --no-audit --no-fund

hooks: ## enable repo git hooks (secret scan + claim check + author check)
	git config core.hooksPath .githooks

context: ## one-shot situational awareness for any agent
	python3 tools/agentctl.py context

board: ## task board with claims
	python3 tools/agentctl.py board
