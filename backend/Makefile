.DEFAULT_GOAL := help

VERSION=0.1-dev
# PROJECT_REGISTRY=registry.thalesdigital.io/fred
PROJECT_REGISTRY=registry.thalesdigital.io/tsn/projects/fred
PROJECT_NAME=fred-backend
PY_PACKAGE=fred# need an underscore here

# Target directories
TARGET=$(CURDIR)/target
VENV=$(CURDIR)/.venv

# Python cmd
PIP=$(VENV)/bin/pip
POETRY=$(VENV)/bin/poetry
PYTHON=$(VENV)/bin/python

# Docker
IMG=$(PROJECT_REGISTRY)/$(PROJECT_NAME):$(VERSION)

# Helm
HELM_ARCHIVE=./fred-0.1.0.tgz

# Project id in GitLab
PROJECT_ID="74328"

# Default env file locations
ENV_DIR?=$(CURDIR)
ENV_FILE?=$(ENV_DIR)/config/.env

LOG_LEVEL ?= INFO

##@ Build

.PHONY: build

build: $(TARGET)/.built ## Build current module

MY_SOURCES=$(shell find $(CURDIR)/$(PY_PACKAGE) -type f -name "*.py" | tr "\n" " ")
$(TARGET)/.built: $(TARGET)/.venv-dependencies $(CURDIR)/poetry.lock $(MY_SOURCES)
	$(info ************  POETRY BUILD DISTRIBUTION AND UPDATE VIRTUALENV ************)
	$(POETRY) version ${VERSION}
	$(POETRY) build
	touch $@

.PHONY: docker-build

docker-build: ## Build the Docker image
	docker build -t $(IMG) .

.PHONY: helm-package

helm-package: ## Package the Helm chart into a chart archive
	helm package helm-chart/

##@ Image publishing

.PHONY: docker-push

docker-push: ## Push Docker image IMG
	docker push $(IMG)

.PHONY: helm-push

helm-push: ## Push the Helm chart to the project registry
	curl --fail-with-body --request POST \
         --form "chart=@${HELM_ARCHIVE}" \
         --user ${GITLAB_USER}:${GITLAB_TOKEN} \
         https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts

##@ Development

$(TARGET)/.venv-created:
	$(info ************  CREATE PYTHON 3 .venv  VIRTUALENV  ************)
	mkdir -p $(TARGET)
	python3 -m venv $(VENV)
	touch $@

$(TARGET)/.venv-dependencies: $(TARGET)/.venv-created
	$(info ************  POETRY BUILD VIRTUALENV FROM SCRATCH ************)
	$(PIP) install -U setuptools'<50' wheel pip
	@# note: line below is intended
	$(PIP) install -U poetry==1.7.1
	@# poetry at this step initializes the .venv with good version of the dependencies
	$(POETRY) run pip install -U pip setuptools'<50' wheel
	touch $@

.PHONY: dev

dev: $(TARGET)/.dev ## Install dependencies in .venv for development

$(TARGET)/.dev: $(TARGET)/.venv-dependencies $(CURDIR)/poetry.lock $(MY_SOURCES)
	$(info ************  POETRY INSTALL DEV DEPENDENCIES ************)
	$(POETRY) install
	touch $@

.PHONY: update

update $(CURDIR)/poetry.lock: $(CURDIR)/pyproject.toml $(TARGET)/.venv-dependencies ## Update poetry.lock
	$(info ************  POETRY UPDATE  ************)
	$(POETRY) update

##@ Clean

.PHONY: clean clean-package clean-pyc clean-test

clean: clean-package clean-pyc clean-test ## Clean everything
	$(info ************  CLEAN  ************)
	rm -rf $(VENV)
	rm -rf $(CURDIR)/.cache
	rm -rf $(CURDIR)/.mypy_cache

clean-package: ## Clean generated packages
	$(info ************  CLEANING DISTRIBUTION  ************)
	rm -rf $(CURDIR)/dist
	rm -rf $(TARGET)

clean-pyc: ## Clean pyc
	$(info ************  CLEANING TEMPORARY FILES  ************)
	-find $(CURDIR) -name '*.pyc' -exec rm -f {} +
	-find $(CURDIR) -name '*.pyo' -exec rm -f {} +
	-find $(CURDIR) -name '*~' -exec rm -f {} +
	-find $(CURDIR) -name '__pycache__' -exec rm -rf {} +

clean-test: ## Clean tests
	$(info ************  CLEANING TEST REPORTS  ************)
	rm -rf $(CURDIR)/.tox/
	rm -rf $(CURDIR)/.coverage
	rm -rf $(CURDIR)/htmlcov/
	rm -rf $(TARGET)/.tested

##@ Run

.PHONY: run 

run: dev ## Run in foreground using the root path '/fred'
	@echo "Using env file: $(ENV_FILE)"
	@[ -f $(ENV_FILE) ] && echo "Env file exists" || echo "Warning: Env file not found at $(ENV_FILE)"
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) ${PY_PACKAGE}/main.py --server.configurationPath ./config/configuration.yaml --server.baseUrlPath /fred

.PHONY: run-config

run-config: dev ## Run with a specific env file (ENV_DIR=/path/to/dir)
	@echo "Using env file: $(ENV_FILE)"
	@[ -f $(ENV_FILE) ] && echo "Env file exists" || echo "Warning: Env file not found at $(ENV_FILE)"
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) ${PY_PACKAGE}/main.py --server.configurationPath ./config/configuration.yaml --server.baseUrlPath /fred

.PHONY: run-local

run-local: dev ## Run with local storage only
	LOG_LEVEL=$(LOG_LEVEL) $(PYTHON) ${PY_PACKAGE}/main.py --server.configurationPath ./config/configuration.yaml --server.baseUrlPath /fred

.PHONY: docker-run

docker-run: ## Run in Docker using the root path '/fred'
	docker run -it \
        -p 8000:8000 \
        -v ~/.kube/:/home/fred-user/.kube/ \
        -v ~/.aws/:/home/fred-user/.aws/ \
        -v $(realpath config/configuration.yaml):/app/configuration.yaml \
        -v $(ENV_FILE):/app/.env \
        -e ENV_FILE=/app/.env \
        $(IMG) --server.configurationPath /app/configuration.yaml --server.baseUrlPath /fred

##@ Tests

.PHONY: test

test: dev ## Run unit tests
	$(info ************  RUNNING TESTS  ************)
	PYTHONPATH=fred $(PYTHON) -m pytest --cov=. --cov-report=html fred/tests

##@ Helpers

.PHONY: help

help:  ## Display help menu
	@awk 'BEGIN {FS = ":.*##"; printf "\033[36m\033[0m\n"} /^[0-9a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)