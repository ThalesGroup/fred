.DEFAULT_GOAL := help

BINARY ?= agentic_bench_client.exe
GO ?= go
ARGS ?=
PACKAGE ?= .
DOCKER ?= docker
IMAGE ?= agentic-bench:dev
REGISTRY ?=
IMAGE_FULL := $(if $(REGISTRY),$(REGISTRY)/,)$(IMAGE)

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
