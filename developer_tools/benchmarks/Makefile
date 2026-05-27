.DEFAULT_GOAL := help

REPO_ROOT := $(abspath $(CURDIR)/../..)
BINARY ?= agentic_bench_client.exe
GO ?= go
ARGS ?=
PACKAGE ?= .
DOCKER ?= docker
REGISTRY ?=
IMAGE_REPOSITORY ?= $(if $(REGISTRY),$(REGISTRY)/,)agentic-bench
IMAGE_TAG ?= dev
IMAGE_FULL := $(IMAGE_REPOSITORY):$(IMAGE_TAG)
K3D_CLUSTER ?= fred
K3D_NAMESPACE ?= fred
HELM_RELEASE ?= agentic-bench
HELM_CHART ?= $(REPO_ROOT)/deploy/charts/agentic-bench
HELM_VALUES ?= $(REPO_ROOT)/deploy/charts/agentic-bench/values.yaml
HELM_VALUES_EXISTING ?= $(REPO_ROOT)/developer_tools/benchmarks/values-existing-agent.yaml

##@ Benchmarks

.PHONY: build
build: tidy ## Build the benchmark binary
	$(GO) build -o $(BINARY) $(PACKAGE)

.PHONY: run
run: check-go ## Run the benchmark (use ARGS='...')
	$(GO) run $(PACKAGE) $(ARGS)

.PHONY: tidy
tidy: check-go ## Sync go.mod/go.sum
	$(GO) mod tidy

##@ Container

.PHONY: docker-build
docker-build: ## Build the benchmark Docker image
	$(DOCKER) build -t $(IMAGE_FULL) .

.PHONY: docker-smoke
docker-smoke: docker-build ## Run -help inside the image
	$(DOCKER) run --rm $(IMAGE_FULL) -help

.PHONY: docker-run
docker-run: ## Run the image against URL (set URL=ws://... and export AGENTIC_TOKEN)
	@if [ -z "$(URL)" ]; then echo "URL is required (e.g. make docker-run URL=ws://host:8000/agentic/v1/chatbot/query/ws)"; exit 1; fi
	$(DOCKER) run --rm -e AGENTIC_TOKEN $(IMAGE_FULL) -url $(URL) $(ARGS)

##@ k3d Deployment

.PHONY: k3d-import
k3d-import: ## Import the benchmark image into the k3d cluster
	@echo "📦 Importing $(IMAGE_FULL) into k3d cluster '$(K3D_CLUSTER)'..."
	k3d image import $(IMAGE_FULL) -c $(K3D_CLUSTER)

.PHONY: k3d-deploy-bench
k3d-deploy-bench: docker-build k3d-import k3d-deploy-bench-only ## Build, import, and deploy the benchmark in existing-agent mode to k3d

.PHONY: k3d-deploy-bench-only
k3d-deploy-bench-only: ## Deploy/upgrade the benchmark chart in existing-agent mode (image must already be in k3d)
	@echo "🚀 Deploying $(HELM_RELEASE) in namespace $(K3D_NAMESPACE)..."
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		--namespace $(K3D_NAMESPACE) \
		--create-namespace \
		-f $(HELM_VALUES) \
		-f $(HELM_VALUES_EXISTING) \
		--set image.repository=$(IMAGE_REPOSITORY) \
		--set image.tag=$(IMAGE_TAG)

##@ Clean

.PHONY: clean
clean: ## Remove built artifacts
	rm -f $(BINARY)

##@ Helpers

.PHONY: check-go
check-go: ## Check Go installation
	@command -v $(GO) >/dev/null 2>&1 || { \
		echo "Go is required. Install Go and ensure 'go' is on PATH."; \
		exit 1; \
	}

##@ Help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z0-9._-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
