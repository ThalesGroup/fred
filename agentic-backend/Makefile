include ../scripts/makefiles/config/INFO-agentic.mk

# === Python Utility ===
include ../scripts/makefiles/python-vars.mk
include ../scripts/makefiles/python-deps.mk
include ../scripts/makefiles/python-run.mk
include ../scripts/makefiles/python-openapi.mk
include ../scripts/makefiles/python-code-quality.mk
include ../scripts/makefiles/python-security.mk
include ../scripts/makefiles/python-test.mk
include ../scripts/makefiles/python-clean.mk
include ../scripts/makefiles/help.mk

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

##@ Run Worker

.PHONY: run-worker
run-worker: dev ## run the Temporal agent worker
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_worker.yaml $(UV) run python -m agentic_backend.main_worker

.PHONY: run-worker-prod
run-worker-prod: dev ## run the Temporal agent worker with production config
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_prod.yaml $(UV) run python -m agentic_backend.main_worker

.PHONY: temporal-key
temporal-key: dev ## generate a Temporal payload encryption key
	$(UV) run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

.PHONY: run-worker-docker
run-worker-docker: ## Run the worker in Docker
	@echo "🚀 Running the worker in Docker..."
	docker run --rm -it \
		--name $(WORKER_CONTAINER_NAME) \
		--network $(WORKER_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		-e CONFIG_FILE=/app/config/configuration_worker.yaml \
		-e ENV_FILE=/app/config/.env \
		--entrypoint python \
		$(IMAGE_FULL) \
		-m agentic_backend.main_worker

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-push
docker-push: ## Push the Docker image
	docker push $(IMAGE_FULL)

.PHONY: run-docker
run-docker: ## Run Agentic API in Docker (uses host network by default)
	@echo "🚀 Running Agentic API in Docker..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

# Docker worker runtime defaults
WORKER_CONTAINER_NAME ?= agentic-worker
WORKER_DOCKER_NETWORK ?= host
API_CONTAINER_NAME ?= agentic-api
API_DOCKER_NETWORK ?= host
