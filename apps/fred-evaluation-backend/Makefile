include ../../scripts/makefiles/config/INFO-fred-evaluation.mk

# === Python Utility ===
include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-run.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-security.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/alembic.mk
include ../../scripts/makefiles/help.mk

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE
CONFIG_FILE ?= ./config/configuration.yaml
export CONFIG_FILE

##@ Run


.PHONY: run-worker
run-worker: dev ## Run the evaluation worker
	ENV_FILE=$(ROOT_DIR)/config/.env $(UV) run python -m fred_evaluation_backend.main_worker

##@ Docker

.PHONY: docker-build-api
docker-build-api: ## Build the API Docker image
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		-f dockerfiles/Dockerfile-api \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-build-worker
docker-build-worker: ## Build the worker Docker image
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		-f dockerfiles/Dockerfile-worker \
		-t $(IMAGE_FULL)-worker \
		$(DOCKER_CONTEXT)

API_DOCKER_NETWORK ?= host
API_CONTAINER_NAME ?= fred-evaluation-api
WORKER_CONTAINER_NAME ?= fred-evaluation-worker
WORKER_DOCKER_NETWORK ?= host