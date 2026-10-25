.DEFAULT_GOAL := help

IMAGE ?= fred-sandbox-broker:review
PORT ?= 8443
ENV_FILE ?= $(CURDIR)/config/.env

.PHONY: help
help:
	@echo "Targets: run, docker-build, run-docker, docker-run, test"

.PHONY: run
run: ## Run the trusted broker locally with its configured TLS and isolated backend
	@set -a; if test -f "$(ENV_FILE)"; then . "$(ENV_FILE)"; fi; set +a; \
	  test -d "$${SANDBOX_TLS_DIR:-}" || { echo "Set SANDBOX_TLS_DIR to an existing broker TLS directory" >&2; exit 2; }; \
	  SANDBOX_TLS_DIR=$$(realpath "$$SANDBOX_TLS_DIR"); export SANDBOX_TLS_DIR; \
	  if test -n "$${SANDBOX_DOCKER_CERT_DIR:-}"; then export DOCKER_CERT_PATH="$$(realpath "$$SANDBOX_DOCKER_CERT_DIR")"; fi; \
	  uv run uvicorn sandbox_broker.main:app --host 127.0.0.1 --port $(PORT) --ssl-certfile "$$SANDBOX_TLS_DIR/tls.crt" --ssl-keyfile "$$SANDBOX_TLS_DIR/tls.key"

.PHONY: docker-build
docker-build: ## Build the broker image using the repository root context
	docker build -f Dockerfile -t $(IMAGE) ../..

.PHONY: run-docker docker-run
run-docker docker-run: ## Run the built image via the hardened Docker Compose profile
	@set -a; if test -f "$(ENV_FILE)"; then . "$(ENV_FILE)"; fi; set +a; \
	  test -d "$${SANDBOX_TLS_DIR:-}" || { echo "Set SANDBOX_TLS_DIR to an existing broker TLS directory" >&2; exit 2; }; \
	  test -d "$${SANDBOX_DOCKER_CERT_DIR:-}" || { echo "Set SANDBOX_DOCKER_CERT_DIR to an existing Docker TLS directory" >&2; exit 2; }; \
	  SANDBOX_TLS_DIR=$$(realpath "$$SANDBOX_TLS_DIR"); export SANDBOX_TLS_DIR; \
	  SANDBOX_DOCKER_CERT_DIR=$$(realpath "$$SANDBOX_DOCKER_CERT_DIR"); export SANDBOX_DOCKER_CERT_DIR; \
	  SANDBOX_BROKER_IMAGE=$(IMAGE) docker compose -f ../../deploy/sandbox/docker-compose.yaml up --no-build sandbox-broker

.PHONY: test
test: ## Run focused broker tests
	uv run --extra dev pytest -q
