CARGO ?= $(HOME)/.cargo/bin/cargo
REGISTRY_URL ?= ghcr.io
REGISTRY_NAMESPACE ?= thalesgroup/fred-agent
IMAGE_NAME ?= monitor
IMAGE_TAG ?= 5.0.0
IMAGE_FULL ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: run code-quality test docker-build
run: ## Start the monitor with configuration from the environment
	$(CARGO) run --locked -p monitor

code-quality: ## Check formatting and lint every monitor target
	$(CARGO) fmt -p monitor --check
	$(CARGO) clippy --locked -p monitor --all-targets -- -D warnings

test: ## Run offline access-boundary and Kubernetes collector tests
	$(CARGO) test --locked -p monitor

docker-build: ## Build the local monitor image from the repository root
	docker build -f dockerfiles/Dockerfile-prod -t $(IMAGE_FULL) ../..

.PHONY: generate-openapi
generate-openapi: ## Generate the monitor contract without running services
	@set -e; tmp=$$(mktemp openapi.json.XXXXXX); \
	trap 'rm -f "$$tmp"' EXIT; \
	$(CARGO) run --quiet --locked -p monitor -- generate-openapi > "$$tmp"; \
	mv "$$tmp" openapi.json
