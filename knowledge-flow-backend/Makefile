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
	CONFIG_FILE="./config/configuration_worker.yaml" \
	$(PYTHON) $(PY_PACKAGE)/main_worker.py

.PHONY: run-worker-docker
run-worker-docker: ## Run an ingestion worker in Docker (Temporal on localhost via host network)
	@echo "🚀 Running the worker in Docker..."
	docker run --rm -it \
		--name $(WORKER_CONTAINER_NAME) \
		--network $(WORKER_DOCKER_NETWORK) \
		-e CONFIG_FILE=/app/config/configuration_worker.yaml \
		-v $(realpath config/.env):/app/config/.env:ro \
		-v $(realpath config/configuration_worker.yaml):/app/config/configuration_worker.yaml:ro \
		--entrypoint python \
		$(IMAGE_FULL) \
		knowledge_flow_backend/main_worker.py

.PHONY: docker-run
docker-run: ## Run the app in Docker
	docker run -it \
		-p $(PORT):$(PORT) \
		-v ~/.kube/:/home/fred-user/.kube/ \
		-v $(realpath config/.env):/app/config/.env \
		-v $(realpath config/configuration.yaml):/app/knowledge-flow-backend/config/configuration.yaml \
		-e CONFIG_FILE=/app/knowledge-flow-backend/config/configuration.yaml \
		$(IMAGE_FULL)

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
