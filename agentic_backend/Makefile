.DEFAULT_GOAL := help

VERSION=0.1.0
PROJECT_NAME=fred-agentic-backend
PY_PACKAGE=app

TARGET=$(CURDIR)/target
VENV=$(CURDIR)/.venv

PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip
UV=$(VENV)/bin/uv

ROOT_DIR := $(realpath $(CURDIR))
# Needed env variable to start app
export ENV_FILE ?= $(ROOT_DIR)/config/.env
export CONFIG_FILE ?= $(ROOT_DIR)/config/configuration.yaml
export LOG_LEVEL ?= info

##@ Setup

$(TARGET)/.venv-created:
	@echo "🔧 Creating virtualenv..."
	mkdir -p $(TARGET)
	python3 -m venv $(VENV)
	touch $@

$(TARGET)/.uv-installed: $(TARGET)/.venv-created
	@echo "📦 Installing uv..."
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install uv
	touch $@

##@ Dependency Management

.PHONY: dev
dev: $(TARGET)/.compiled ## Install from compiled lock
	@echo "✅ Dependencies installed using uv."
$(TARGET)/.compiled: pyproject.toml $(TARGET)/.uv-installed
	$(UV) sync --extra dev
	touch $@

.PHONY: update
update: $(TARGET)/.uv-installed ## Re-resolve and update all dependencies
	$(UV) sync
	touch $(TARGET)/.compiled

##@ Run

.PHONY: run-local
run-local: PORT ?= 8000
run-local: UVICORN_FACTORY ?= app.main:create_app
run-local: UVICORN_LOOP ?= asyncio
run-local: ## Run the app assuming dependencies already exist
	$(UV) run uvicorn \
		--factory ${UVICORN_FACTORY} \
		--port ${PORT} \
		--env-file ${ENV_FILE} \
		--log-level ${LOG_LEVEL} \
		--loop ${UVICORN_LOOP} \
		--reload

.PHONY: run
run: dev run-local ## Run the app from source

##@ Clean

.PHONY: clean

clean: ## Remove virtualenv and build artifacts
	@echo "🧹 Cleaning project..."
	rm -rf $(VENV) $(TARGET) .mypy_cache .pytest_cache .coverage htmlcov .tox

##@ Tests

.PHONY: list-tests
list-tests: dev ## List all available test names using pytest
	@echo "************ AVAILABLE TESTS ************"
	$(VENV)/bin/pytest --collect-only -q | grep -v "<Module"

.PHONY: test test-app test-processors

.PHONY: test-one
test-one: dev ## Run a specific test by setting TEST=...
	@if [ -z "$(TEST)" ]; then \
		echo "❌ Please provide a test path using: make test-one TEST=path::to::test"; \
		exit 1; \
	fi
	$(VENV)/bin/pytest -v $(subst ::,::,$(TEST))

test: dev ## Run all tests
	@echo "************ TESTING APP ************"
	$(VENV)/bin/pytest --cov=. --cov-config=.coveragerc --cov-report=html app
	@echo "✅ Coverage report: htmlcov/index.html"
	@xdg-open htmlcov/index.html || echo "📎 Open manually htmlcov/index.html"

##@ Help

.PHONY: help

help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mAvailable targets:\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
