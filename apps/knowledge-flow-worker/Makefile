include ../../scripts/makefiles/config/INFO-knowledge-flow-worker.mk

# === Python Utility ===
include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-config-schema.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-security.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

# Put the venv's bin/ on PATH for every recipe in this project.
#
# Why: the DOCX processor shells out to `pandoc` by name, and the only pandoc we
# ship is the one bundled by the `pypandoc-binary` dependency, exposed as
# $(VENV)/bin/pandoc. Running $(PYTHON) by absolute path does NOT put $(VENV)/bin
# on PATH — only `source .venv/bin/activate` does — so a locally started worker
# died with `FileNotFoundError: 'pandoc'` while the binary sat unused in the venv.
# The Docker images already do exactly this (`ENV PATH="/app/venv/bin:$PATH"`);
# this makes local runs behave the same. Guarded so recursive make does not
# prepend it twice.
ifeq (,$(findstring $(VENV)/bin:,$(PATH)))
export PATH := $(VENV)/bin:$(PATH)
endif

PADDLE_MODELS_DIR ?= ./models

##@ Run

.PHONY: download-models
download-models: dev ## Download ML models required by the PDF processor
	@echo "📦 Downloading ML models to $(PADDLE_MODELS_DIR)..."
	@mkdir -p $(PADDLE_MODELS_DIR)
	$(PYTHON) $(ROOT_DIR)/../../scripts/download_models.py --models-dir $(PADDLE_MODELS_DIR)

.PHONY: tools-check
tools-check:
	@if ! command -v pandoc >/dev/null 2>&1; then \
		echo "================================================================================"; \
		echo "WARNING: pandoc not found on PATH. Doc ingestion (markdown/PDF conversions) will fail locally."; \
		echo "It normally comes from the pypandoc-binary dependency ($(VENV)/bin/pandoc):"; \
		echo "run 'make dev' to install it, or install a system pandoc."; \
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
run-worker: export KF_WORKER_METRICS_PORT ?= 9112
run-worker: dev tools-check download-models ## Run an ingestion worker (requires Temporal daemon)
	@echo "🚀 Running the worker..."
	PYTHONPATH=. \
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) $(PY_PACKAGE)/main.py

# Per-role worker, for running the four groups as separate processes locally —
# the only way to observe the memory isolation a single multi-role worker cannot
# show. The configuration is derived into target/ from configuration_worker.yaml,
# which is never modified: only the role, the metrics port (four processes would
# otherwise fight over one) and the activity concurrency differ.
ROLE ?= common
_ROLE_CONFIG := $(CURDIR)/target/worker-roles/configuration_worker_$(ROLE).yaml

.PHONY: run-worker-role
run-worker-role: dev tools-check download-models ## Run one worker role (ROLE=common|fast|medium|rich)
	@mkdir -p $(dir $(_ROLE_CONFIG))
	$(PYTHON) $(CURDIR)/../../scripts/derive_worker_role_config.py \
		--source $(CURDIR)/config/configuration_worker.yaml \
		--role $(ROLE) \
		--output $(_ROLE_CONFIG)
	@echo "🚀 Running the $(ROLE) worker..."
	PYTHONPATH=. \
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	CONFIG_FILE=$(_ROLE_CONFIG) \
	$(PYTHON) $(PY_PACKAGE)/main.py

.PHONY: run-worker-docker
run-worker-docker: ## Run an ingestion worker in Docker (Temporal on localhost via host network)
	@echo "🚀 Running the worker in Docker..."
	docker run --rm -it \
		--name $(WORKER_CONTAINER_NAME) \
		--network $(WORKER_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		--env-file $(realpath config)/.env \
		-e CONFIG_FILE=./config/configuration_worker.yaml \
		--entrypoint python \
		$(IMAGE_FULL) \
		knowledge_flow_worker/main.py

##@ Docker

INSTALL_PYMUPDF ?= false

.PHONY: docker-build
docker-build: ## Build the worker image (INSTALL_PYMUPDF=true enables the optional variant)
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		$(DOCKER_CA_SECRET) \
		--build-arg INSTALL_PYMUPDF=$(INSTALL_PYMUPDF) \
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
TEST_STATE_DIR ?= ./.fred-test
TEST_DOCKER_USER ?= $(shell id -u):$(shell id -g)

##@ System dependencies

.PHONY: libreoffice-check
libreoffice-check:
	@if ! command -v soffice >/dev/null 2>&1; then \
		echo "================================================================================"; \
		echo "WARNING: LibreOffice (soffice) not found on PATH. Excel recalc and legacy"; \
		echo "Office (.doc/.ppt/.odt) conversions will fail locally."; \
		echo "Install it: make install-system-deps   (or: sudo apt-get install -y libreoffice)"; \
		echo "================================================================================"; \
	fi

# Surface a missing LibreOffice before the API server starts (make run -> run-local)
# and fold the same probe into the aggregate tools-check the worker already runs.
# soffice is the canonical binary the processors invoke; it ships in every Docker image.
tools-check: libreoffice-check

.PHONY: install-system-deps
install-system-deps: ## Install host system deps for document ingestion (Debian/Ubuntu, needs sudo)
	@echo "📦 Installing system dependencies (LibreOffice, pandoc, poppler-utils, inkscape)..."
	sudo apt-get update
	sudo apt-get install -y libreoffice pandoc poppler-utils inkscape

.PHONY: run
run: run-worker

CONTROL_PLANE_PROCESSING_FIXTURES := $(ROOT_DIR)/../control-plane/tests/fixtures/processing

.PHONY: generate-control-plane-contract
generate-control-plane-contract: dev ## Regenerate the control-plane integration fixture from its worker configuration
	@set -e; fixture="$(CONTROL_PLANE_PROCESSING_FIXTURES)/worker-contract.json"; \
	tmp=$$(mktemp "$$fixture.XXXXXX"); trap 'rm -f "$$tmp"' EXIT; \
	$(PYTHON) -m knowledge_flow_worker.features.scheduler.export_contract \
		--configuration "$(CONTROL_PLANE_PROCESSING_FIXTURES)/worker-configuration.yaml" > "$$tmp"; \
	mv "$$tmp" "$$fixture"
