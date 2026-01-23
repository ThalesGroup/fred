.DEFAULT_GOAL := help

BINARY ?= agentic_bench_client.exe
GO ?= go
ARGS ?=
PACKAGE ?= .

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
