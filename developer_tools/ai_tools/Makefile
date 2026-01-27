.DEFAULT_GOAL := help

ROOT_DIR := $(realpath $(CURDIR))
PROJECT_ROOT=$(ROOT_DIR)/..
TARGET   := $(ROOT_DIR)/target
VENV     := $(ROOT_DIR)/.venv
PIP      := $(VENV)/bin/pip
PYTHON   := $(VENV)/bin/python
UV       := $(VENV)/bin/uv

ENV_FILE := $(ROOT_DIR)/config/.env
LOG_LEVEL ?= INFO

##@ Setup

$(TARGET)/.venv-created:
	@echo "🔧 Creating virtualenv in developer_tools..."
	mkdir -p $(TARGET)
	python3 -m venv $(VENV)
	touch $@

$(TARGET)/.uv-installed: $(TARGET)/.venv-created
	@echo "📦 Installing uv..."
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install uv
	touch $@

##@ Dependencies

.PHONY: dev
dev: $(TARGET)/.compiled ## Install dependencies
	@echo "✅ Dependencies installed using uv."

$(TARGET)/.compiled: pyproject.toml $(TARGET)/.uv-installed
	$(UV) sync --extra dev
	touch $@

##@ Review Commands

.PHONY: review-pull-request
review-code-pull-request: dev ## Review committed Python changes
	@echo "🤖 Reviewing Python changes (committed)..."
	LOG_LEVEL=$(LOG_LEVEL) \
	PROJECT_ROOT=$(PROJECT_ROOT) \
	$(PYTHON) ai_code_review.py --mode committed

.PHONY: review-uncommitted
review-code-uncommitted: dev ## Review staged Python changes
	@echo "🤖 Reviewing Python changes (staged)..."
	LOG_LEVEL=$(LOG_LEVEL) \
	PROJECT_ROOT=$(PROJECT_ROOT) \
	$(PYTHON) ai_code_review.py --mode uncommitted

.PHONY: review-all
review-code-all: dev ## Review all modified Python files
	@echo "🤖 Reviewing all Python files..."
	LOG_LEVEL=$(LOG_LEVEL) \
	PROJECT_ROOT=$(PROJECT_ROOT) \
	$(PYTHON) ai_code_review.py --mode all

.PHONY: review-deploy
review-deploy: dev ## Review config vs deployment consistency
	@echo "🛠️ Reviewing backend ↔️ deploy consistency..."
	LOG_LEVEL=$(LOG_LEVEL) \
	PROJECT_ROOT=$(PROJECT_ROOT) \
	$(PYTHON) ai_deployment_review.py --path ..

.PHONY: check-headers
check-headers: ## Check and add missing Apache 2.0 headers
	@echo "🔍 Checking and adding Apache 2.0 headers in project..."
	PROJECT_ROOT=$(PROJECT_ROOT) \
	bash check_and_add_apachev2_headers.sh $(PROJECT_ROOT)

##@ Clean

.PHONY: clean
clean: ## Clean venv and target artifacts
	rm -rf $(VENV) $(TARGET)

##@ Help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z0-9._-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
