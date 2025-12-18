# Makefile

PY_PACKAGE ?= main
HOST ?= 0.0.0.0
# Prefer (in order): explicit PORT, exported APP_PORT, APP_PORT from local .env, fallback 8080.
ENV_FILE ?= .env
APP_PORT_FILE := $(shell [ -f "$(ENV_FILE)" ] && sed -n 's/^APP_PORT=//p' "$(ENV_FILE)" | tail -n 1 | tr -d '"' )
PORT ?= $(if $(strip $(APP_PORT)),$(APP_PORT),$(if $(strip $(APP_PORT_FILE)),$(APP_PORT_FILE),8080))
LOG_LEVEL ?= info
UVICORN_LOOP ?= asyncio
VENV ?= .venv

# Détecte automatiquement l'exécutable Python dans le venv
ifeq ($(OS),Windows_NT)
UV := $(VENV)/Scripts/python.exe
PIP := $(VENV)/Scripts/pip.exe
else
UV := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
endif

.PHONY: install
install:
	@echo "📦 Creating virtualenv if needed..."
	@test -d $(VENV) || python -m venv $(VENV)
	@.venv/bin/uv sync

.PHONY: run-local
run-local: UVICORN_FACTORY ?= ${PY_PACKAGE}:create_app
run-local: ## Run the app assuming dependencies already exist
	@echo "💻 Running FastAPI locally..."
	@$(UV) -m uvicorn \
		${UVICORN_FACTORY} \
		--factory \
		--host ${HOST} \
		--port 9666 \
		--log-level ${LOG_LEVEL} \
		--loop ${UVICORN_LOOP}

.PHONY: run
run: install run-local
