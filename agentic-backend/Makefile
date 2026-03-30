include ../scripts/makefiles/config/INFO-agentic.mk

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

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

##@ Run Worker

.PHONY: run-worker
run-worker: dev ## run the Temporal agent worker
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_worker.yaml $(UV) run python -m agentic_backend.main_worker

.PHONY: run-worker-prod
run-worker-prod: dev ## run the Temporal agent worker with production config
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_prod.yaml $(UV) run python -m agentic_backend.main_worker

.PHONY: temporal-key
temporal-key: dev ## generate a Temporal payload encryption key
	$(UV) run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

.PHONY: run-worker-docker
run-worker-docker: ## Run the worker in Docker
	@echo "🚀 Running the worker in Docker..."
	docker run --rm -it \
		--name $(WORKER_CONTAINER_NAME) \
		--network $(WORKER_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		-e CONFIG_FILE=/app/config/configuration_worker.yaml \
		-e ENV_FILE=/app/config/.env \
		--entrypoint python \
		$(IMAGE_FULL) \
		-m agentic_backend.main_worker

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-push
docker-push: ## Push the Docker image
	docker push $(IMAGE_FULL)

.PHONY: run-docker
run-docker: ## Run Agentic API in Docker (uses host network by default)
	@echo "🚀 Running Agentic API in Docker..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

##@ Agent Evaluation
#
# Runs end-to-end evaluations against a live Fred server using DeepEval.
#
# Prerequisites:
#   1. Knowledge Flow server running  (tabular data must be loaded)
#   2. config/.env present            (sourced automatically — provides KEYCLOAK_AGENTIC_CLIENT_SECRET)
#
# Token resolution order (first match wins):
#   1. AGENTIC_TOKEN env var already set → used as-is (forwarded to KF server for MCP auth)
#   2. KEYCLOAK_AGENTIC_CLIENT_SECRET found in config/.env → auto-fetched via client_credentials
#   3. Neither → empty token (works when auth is disabled, e.g. local dev)
#
# Each agent has its own eval_config.yaml next to its evaluator.
# Edit that file to change dataset, configuration file, or judge model.
#
# Override Keycloak coordinates if your deployment differs from configuration.yaml:
#   EVAL_KEYCLOAK_URL=https://auth.prod.example.com/realms/app make eval-sql-agent

# Keycloak coordinates — defaults match configuration.yaml; override per environment.
EVAL_KEYCLOAK_URL    ?= http://app-keycloak:8080/realms/app
EVAL_KEYCLOAK_CLIENT ?= agentic

_EVAL_SQL_CONFIG := agentic_backend/tests/agents/sql/eval_config.yaml
_EVAL_SQL_SCRIPT := agentic_backend/tests/agents/sql/sql_analyst_evaluation.py

.PHONY: eval-sql-agent
eval-sql-agent: dev ## Evaluate the V2 SQL analyst agent  [auto-fetches token from config/.env]
	@set -a && . $(ENV_FILE) && set +a; \
	if [ -z "$$AGENTIC_TOKEN" ] && [ -n "$$KEYCLOAK_AGENTIC_CLIENT_SECRET" ]; then \
	    echo "🔑 Fetching token from Keycloak ($(EVAL_KEYCLOAK_URL))..."; \
	    AGENTIC_TOKEN=$$(curl -sf \
	        "$(EVAL_KEYCLOAK_URL)/protocol/openid-connect/token" \
	        --data-urlencode "client_id=$(EVAL_KEYCLOAK_CLIENT)" \
	        --data-urlencode "client_secret=$$KEYCLOAK_AGENTIC_CLIENT_SECRET" \
	        --data-urlencode "grant_type=client_credentials" \
	        | $(PYTHON) -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null \
	    ); \
	    if [ -n "$$AGENTIC_TOKEN" ]; then \
	        echo "✅ Token obtained."; \
	    else \
	        echo "⚠️  Keycloak unreachable or auth failed — proceeding without token (ok if auth is disabled locally)."; \
	    fi; \
	fi; \
	AGENTIC_TOKEN=$$AGENTIC_TOKEN $(PYTHON) $(_EVAL_SQL_SCRIPT) --config $(_EVAL_SQL_CONFIG)

# Docker worker runtime defaults
WORKER_CONTAINER_NAME ?= agentic-worker
WORKER_DOCKER_NETWORK ?= host
API_CONTAINER_NAME ?= agentic-api
API_DOCKER_NETWORK ?= host
