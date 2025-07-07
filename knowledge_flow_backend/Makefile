.DEFAULT_GOAL := help

VERSION=0.1-dev
PROJECT_REGISTRY=registry.thalesdigital.io/tsn/projects/knowledge_flow_app
PROJECT_NAME=knowledge-flow
PY_PACKAGE=knowledge_flow_app

ROOT_DIR := $(realpath $(CURDIR))
ENV_FILE := $(ROOT_DIR)/config/.env

TARGET=$(CURDIR)/target
VENV=$(CURDIR)/.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
UV=uv

IMG=$(PROJECT_REGISTRY)/$(PROJECT_NAME):$(VERSION)
HELM_ARCHIVE=./knowledge_flow_app-0.1.0.tgz
PROJECT_ID="74648"

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

##@ Build

.PHONY: build

build: dev $(TARGET)/.built ## Build current module

$(TARGET)/.built:
	@echo "************ UV BUILD PLACEHOLDER ************"
	touch $@

.PHONY: docker-build

docker-build: ## Build the Docker image
	docker build -t $(IMG) .

.PHONY: helm-package

helm-package: ## Package the Helm chart
	helm package helm-chart/

##@ Image publishing

.PHONY: docker-push

docker-push: ## Push Docker image IMG
	docker push $(IMG)

.PHONY: helm-push

helm-push: ## Push Helm chart to GitLab package registry
	curl --fail-with-body --request POST \
		 --form "chart=@${HELM_ARCHIVE}" \
		 --user ${GITLAB_USER}:${GITLAB_TOKEN} \
		 https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts

##@ Run

.PHONY: run

run: dev ## Run the app from source
	PYTHONPATH=. \
	ENV_FILE="$(ENV_FILE)" LOG_LEVEL="$(LOG_LEVEL)" \
	$(PYTHON) ${PY_PACKAGE}/main.py --config-path ./config/configuration.yaml

.PHONY: docker-run

docker-run: ## Run the app in Docker
	docker run -it \
		-p 8111:8111 \
		-v ~/.kube/:/home/fred-user/.kube/ \
		-v ~/.aws/:/home/fred-user/.aws/ \
		-v $(realpath knowledge_flow_app/config/configuration.yaml):/app/configuration.yaml \
		-e LOG_LEVEL="$(LOG_LEVEL)" \
		$(IMG) --config-path /app/configuration.yaml

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
	$(VENV)/bin/pytest --cov=. --cov-config=.coveragerc --cov-report=html knowledge_flow_app
	@echo "✅ Coverage report: htmlcov/index.html"
	@xdg-open htmlcov/index.html || echo "📎 Open manually htmlcov/index.html"

##@ Clean

.PHONY: clean clean-package clean-pyc clean-test

clean: clean-package clean-pyc clean-test ## Clean all build/test artifacts
	@echo "🧹 Cleaning project..."
	rm -rf $(VENV)
	rm -rf .cache .mypy_cache

clean-package: ## Clean distribution artifacts
	@echo "************ CLEANING DISTRIBUTION ************"
	rm -rf dist
	rm -rf $(TARGET)

clean-pyc: ## Clean Python bytecode
	@echo "************ CLEANING PYTHON CACHE ************"
	find . -name '*.pyc' -delete
	find . -name '*.pyo' -delete
	find . -name '*~' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +

clean-test: ## Clean test cache
	@echo "************ CLEANING TESTS ************"
	rm -rf .tox .coverage htmlcov $(TARGET)/.tested

##@ Code quality

.PHONY: lint lint-fix format sast code-quality

lint: ## Run the linter (ruff) on all the project
	@echo "************ Executing Ruff linter ************"
	$(UV) run ruff check

lint-fix: ## Run the linter (ruff) to fix all the auto fixable linter error
	@echo "************ Executing Ruff linter and apply fix if possible ************"
	$(UV) run ruff check --fix

format: ## Run the formatter (ruff)
	@echo "************ Executing Ruff formatter ************"
	$(UV) run ruff format

sast: ## Run bandit
	@echo "************ Executing Ruff formatter with rules B101 (assert_used) and B108 (hardcoded_tmp_directory) ignored ************"
	$(UV) run bandit -r knowledge_flow_app -s B101,B108

code-quality: ## Run all pre-commit checks
	@echo "************ Executing pre-commit ************"
	$(UV) run pre-commit run --all-files

##@ Review 

.PHONY: review-pull-request
review-pull-request: dev ## Run AI-based PR review locally
	@echo "🤖 Reviewing Python changes using AI..."
	$(PYTHON) developer_tools/ai_review_pull_request.py --mode committed

.PHONY: review-uncommitted
review-uncommitted: dev ## Run AI-based PR review locally
	@echo "🤖 Reviewing Python changes using AI..."
	$(PYTHON) developer_tools/ai_review_pull_request.py --mode uncommitted

.PHONY: review-all
review-all: dev ## Run AI-based PR review locally
	@echo "🤖 Reviewing Python changes using AI..."
	$(PYTHON) developer_tools/ai_review_pull_request.py --mode all

##@ Help

.PHONY: help

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z0-9._-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
