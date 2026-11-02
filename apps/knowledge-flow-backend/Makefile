include ../../scripts/makefiles/config/INFO-knowledge-flow.mk

# === Python Utility ===
include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-run.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/python-config-schema.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-security.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

.PHONY: run-docker
run-docker: ## Run Knowledge Flow API in Docker (uses host network by default)
	@echo "🚀 Running Knowledge Flow API in Docker..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		-v ~/.kube/:/home/fred-user/.kube/:ro \
		$(IMAGE_FULL)

.PHONY: run-docker-test
run-docker-test: reset-test-state ## Run Knowledge Flow API in Docker with configuration_test.yaml
	@echo "🚀 Running Knowledge Flow API in Docker (configuration_test.yaml)..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--user $(TEST_DOCKER_USER) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		-v $(abspath $(TEST_STATE_DIR)):/app/.fred-test \
		-v ~/.kube/:/home/fred-user/.kube/:ro \
		-e CONFIG_FILE=/app/config/configuration_test.yaml \
		-e ENV_FILE=/app/config/.env \
		-e HOME=/app/.fred-test \
		-e NUMBA_CACHE_DIR=/app/.fred-test/numba-cache \
		-e XDG_CACHE_HOME=/app/.fred-test/.cache \
		-e HF_HOME=/app/.fred-test/.cache/huggingface \
		-e HUGGINGFACE_HUB_CACHE=/app/.fred-test/.cache/huggingface/hub \
		-e HF_HUB_CACHE=/app/.fred-test/.cache/huggingface/hub \
		-e SENTENCE_TRANSFORMERS_HOME=/app/.fred-test/.cache/huggingface \
		$(IMAGE_FULL)

.PHONY: reset-test-state
reset-test-state: ## Reset local test state used by configuration_test.yaml
	@echo "🧹 Resetting KF test state at $(abspath $(TEST_STATE_DIR))"
	rm -rf "$(abspath $(TEST_STATE_DIR))"
	mkdir -p "$(abspath $(TEST_STATE_DIR))"
	mkdir -p "$(abspath $(TEST_STATE_DIR))/.cache/huggingface/hub"
	mkdir -p "$(abspath $(TEST_STATE_DIR))/numba-cache"

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		$(DOCKER_CA_SECRET) \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-push
docker-push: ## Push the Docker image
	docker push $(IMAGE_FULL)

##@ Helm

.PHONY: helm-package
helm-package: ## Package the Helm chart
	helm package helm-chart/

.PHONY: helm-push
helm-push: ## Push Helm chart to GitLab package registry
	curl --fail-with-body --request POST \
		--form "chart=@${HELM_ARCHIVE}" \
		--user ${GITLAB_USER}:${GITLAB_TOKEN} \
		https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts

##@ Build

.PHONY: build
build: dev $(TARGET)/.built ## Build current module

$(TARGET)/.built:
	@echo "************ UV BUILD PLACEHOLDER ************"
	touch $@

# API Docker runtime defaults
API_CONTAINER_NAME ?= kf-api
API_DOCKER_NETWORK ?= host
TEST_STATE_DIR ?= ./.fred-test
TEST_DOCKER_USER ?= $(shell id -u):$(shell id -g)

