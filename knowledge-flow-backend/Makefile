include ../scripts/makefiles/config/INFO-knowledge-flow.mk

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

##@ Run

.PHONY: tools-check
tools-check:
	@if ! command -v pandoc >/dev/null 2>&1; then \
		echo "================================================================================"; \
		echo "WARNING: pandoc not found on PATH. Doc ingestion (markdown/PDF conversions) will fail locally."; \
		echo "Install pandoc or use the provided Docker image."; \
		echo "================================================================================"; \
	fi
	@if ! command -v pdfinfo >/dev/null 2>&1; then \
		echo "================================================================================"; \
		echo "WARNING: poppler/pdfinfo not found on PATH. PDF parsing via unstructured/pdf2image can fail locally."; \
		echo "Install poppler-utils (provides pdfinfo) or use the provided Docker image."; \
		echo "================================================================================"; \
	fi
	@if ! command -v inkscape >/dev/null 2>&1; then \
		echo "================================================================================"; \
		echo "WARNING: inkscape not found on PATH. EMF/SVG conversions will be skipped or fail locally."; \
		echo "Install inkscape or use the provided Docker image."; \
		echo "================================================================================"; \
	fi

.PHONY: run-worker
run-worker: dev tools-check ## Run an ingestion worker (requires Temporal daemon)
	@echo "🚀 Running the worker..."
	PYTHONPATH=. \
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) $(PY_PACKAGE)/main_worker.py

.PHONY: run-worker-docker
run-worker-docker: ## Run an ingestion worker in Docker (Temporal on localhost via host network)
	@echo "🚀 Running the worker in Docker..."
	docker run --rm -it \
		--name $(WORKER_CONTAINER_NAME) \
		--network $(WORKER_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		--entrypoint python \
		$(IMAGE_FULL) \
		knowledge_flow_backend/main_worker.py

.PHONY: markdown-profile-test
markdown-profile-test: ## Run recursive markdown profile test script (set INPUT_DIR=... optionally PROFILES=fast,medium,rich OUTPUT_DIR=...)
	@if [ -z "$(INPUT_DIR)" ]; then \
		echo "Usage: make markdown-profile-test INPUT_DIR=/path/to/files [PROFILES=fast,medium,rich] [OUTPUT_DIR=./target/markdown-profile-tests] [BASE_URL=http://localhost:8111/knowledge-flow/v1]"; \
		exit 2; \
	fi
	./tests/scripts/test_markdown_profiles.sh \
		--input-dir "$(INPUT_DIR)" \
		--profiles "$(PROFILES)" \
		--output-dir "$(OUTPUT_DIR)" \
		--base-url "$(BASE_URL)"

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

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

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

# Docker worker runtime defaults
WORKER_CONTAINER_NAME ?= kf-worker
WORKER_DOCKER_NETWORK ?= host
API_CONTAINER_NAME ?= kf-api
API_DOCKER_NETWORK ?= host
PROFILES ?= fast,medium,rich
OUTPUT_DIR ?= ./target/markdown-profile-tests
BASE_URL ?= http://localhost:8111/knowledge-flow/v1
TEST_STATE_DIR ?= ./.fred-test
TEST_DOCKER_USER ?= $(shell id -u):$(shell id -g)
