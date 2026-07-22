include ../../scripts/makefiles/config/INFO-fred-agents.mk


include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-run.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/python-config-schema.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: run-docker
run-docker: ## Run fred-agents in Docker (uses host network by default)
	@echo "🚀 Running fred-agents in Docker..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

PORT ?= 8000

.PHONY: cli
cli: dev ## Open the interactive CLI for a running agent pod
	ENV_FILE=$(CURDIR)/config/.env VIRTUAL_ENV= $(UV) run fred-agents-cli

# Docker runtime defaults
API_CONTAINER_NAME ?= fred-agents-api
API_DOCKER_NETWORK ?= host
