.DEFAULT_GOAL := help

VERSION=0.1.0
PROJECT_NAME=fred-agentic-backend
PY_PACKAGE=app

TARGET=$(CURDIR)/target
VENV=$(CURDIR)/.venv

PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip
UV=$(VENV)/bin/uv

ENV_DIR?=$(CURDIR)
ENV_FILE?=$(ENV_DIR)/config/.env
LOG_LEVEL?=INFO

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

.PHONY: run

run: dev
	@echo "🚀 Running the app..."
	PYTHONPATH=. \
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) ${PY_PACKAGE}/main.py --server.configurationPath ./config/configuration.yaml

##@ Clean

.PHONY: clean

clean: ## Remove virtualenv and build artifacts
	@echo "🧹 Cleaning project..."
	rm -rf $(VENV) $(TARGET) .mypy_cache .pytest_cache .coverage htmlcov .tox

##@ Testing

.PHONY: test
test: dev  ## Run tests for test_translate_response_metadata.py
	@echo "🧪 Running test_translate_response_metadata.py..."
	PYTHONPATH=$(CURDIR)/app $(VENV)/bin/pytest --maxfail=5 --disable-warnings -q app/tests/test_translate_response_metadata.py

##@ Help

.PHONY: help

help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mAvailable targets:\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
