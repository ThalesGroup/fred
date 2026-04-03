include ../scripts/makefiles/config/INFO-control-plane.mk

# === Python Utility ===
include ../scripts/makefiles/python-vars.mk
include ../scripts/makefiles/python-deps.mk
include ../scripts/makefiles/python-run.mk
include ../scripts/makefiles/python-openapi.mk
include ../scripts/makefiles/python-code-quality.mk
include ../scripts/makefiles/python-security.mk
include ../scripts/makefiles/python-test.mk
include ../scripts/makefiles/python-clean.mk
include ../scripts/makefiles/alembic.mk
include ../scripts/makefiles/help.mk

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

##@ Dev Helpers

CONTROL_PLANE_BASE_URL ?= http://localhost:8222/control-plane/v1
KEYCLOAK_REALM_URL ?= http://localhost:8080/realms/app
KEYCLOAK_APP_CLIENT_ID ?= app
KEYCLOAK_DEV_USERNAME ?= alice
KEYCLOAK_DEV_PASSWORD ?=
CP_NEW_USER_USERNAME ?= test1
CP_NEW_USER_EMAIL ?= test1@app.com
CP_NEW_USER_PASSWORD ?=

.PHONY: create-test-user
create-test-user: dev ## Create a user in control-plane without manual bearer token copy/paste
	@set -a; \
	if [ -f "$(ENV_FILE)" ]; then . "$(ENV_FILE)"; fi; \
	set +a; \
	KEYCLOAK_DEV_PASSWORD_RESOLVED="$(KEYCLOAK_DEV_PASSWORD)"; \
	if [ -z "$$KEYCLOAK_DEV_PASSWORD_RESOLVED" ]; then \
		KEYCLOAK_DEV_PASSWORD_RESOLVED="$$KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET"; \
	fi; \
	CP_NEW_USER_PASSWORD_RESOLVED="$(CP_NEW_USER_PASSWORD)"; \
	if [ -z "$$CP_NEW_USER_PASSWORD_RESOLVED" ]; then \
		CP_NEW_USER_PASSWORD_RESOLVED="$$KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET"; \
	fi; \
	if [ -z "$$KEYCLOAK_DEV_PASSWORD_RESOLVED" ]; then \
		echo "❌ Missing KEYCLOAK_DEV_PASSWORD (and no fallback found in $(ENV_FILE))"; \
		echo "   Set KEYCLOAK_DEV_PASSWORD or KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET in $(ENV_FILE)."; \
		exit 1; \
	fi; \
	if [ -z "$$CP_NEW_USER_PASSWORD_RESOLVED" ]; then \
		echo "❌ Missing CP_NEW_USER_PASSWORD (and no fallback found in $(ENV_FILE))"; \
		echo "   Set CP_NEW_USER_PASSWORD or KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET in $(ENV_FILE)."; \
		exit 1; \
	fi; \
	TOKEN_RESPONSE=$$(curl -sS -X POST "$(KEYCLOAK_REALM_URL)/protocol/openid-connect/token" \
		-H "Content-Type: application/x-www-form-urlencoded" \
		-d "grant_type=password" \
		-d "client_id=$(KEYCLOAK_APP_CLIENT_ID)" \
		-d "username=$(KEYCLOAK_DEV_USERNAME)" \
		-d "password=$$KEYCLOAK_DEV_PASSWORD_RESOLVED" \
	); \
	TOKEN=$$(printf '%s' "$$TOKEN_RESPONSE" \
		| sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
		| head -n 1); \
	if [ -z "$$TOKEN" ]; then \
		TOKEN_ERROR_CODE=$$(printf '%s' "$$TOKEN_RESPONSE" \
			| sed -n 's/.*"error"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
			| head -n 1); \
		TOKEN_ERROR_DESCRIPTION=$$(printf '%s' "$$TOKEN_RESPONSE" \
			| sed -n 's/.*"error_description"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
			| head -n 1); \
		if [ -n "$$TOKEN_ERROR_CODE" ] || [ -n "$$TOKEN_ERROR_DESCRIPTION" ]; then \
			TOKEN_ERROR="$$TOKEN_ERROR_CODE"; \
			if [ -n "$$TOKEN_ERROR_DESCRIPTION" ]; then \
				TOKEN_ERROR="$$TOKEN_ERROR: $$TOKEN_ERROR_DESCRIPTION"; \
			fi; \
		else \
			TOKEN_ERROR=$$(printf '%s' "$$TOKEN_RESPONSE" | cut -c1-400); \
		fi; \
		echo "❌ Failed to obtain Keycloak access token."; \
		echo "   realm_url=$(KEYCLOAK_REALM_URL)"; \
		echo "   client_id=$(KEYCLOAK_APP_CLIENT_ID)"; \
		echo "   username=$(KEYCLOAK_DEV_USERNAME)"; \
		echo "   keycloak_error=$$TOKEN_ERROR"; \
		exit 1; \
	fi; \
	echo "ℹ️  Creating user $(CP_NEW_USER_USERNAME) via control-plane..."; \
	curl -sS -X POST "$(CONTROL_PLANE_BASE_URL)/users" \
		-H "Authorization: Bearer $$TOKEN" \
		-H "Content-Type: application/json" \
		-d "{\"username\":\"$(CP_NEW_USER_USERNAME)\",\"email\":\"$(CP_NEW_USER_EMAIL)\",\"password\":\"$$CP_NEW_USER_PASSWORD_RESOLVED\",\"enabled\":true}" \
		| $(UV) run python -m json.tool

##@ Run Worker

.PHONY: run-worker
run-worker: dev ## run the Temporal control-plane worker
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_worker.yaml $(UV) run python -m control_plane_backend.main_worker

.PHONY: run-worker-prod
run-worker-prod: dev ## run the Temporal control-plane worker with production config
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_prod.yaml $(UV) run python -m control_plane_backend.main_worker

.PHONY: run-worker-docker
run-worker-docker: ## Run the worker in Docker
	@echo "Running the worker in Docker..."
	docker run --rm -it \
		--name $(WORKER_CONTAINER_NAME) \
		--network $(WORKER_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		-e CONFIG_FILE=/app/config/configuration_worker.yaml \
		-e ENV_FILE=/app/config/.env \
		--entrypoint python \
		$(IMAGE_FULL) \
		-m control_plane_backend.main_worker

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
run-docker: ## Run control-plane API in Docker (uses host network by default)
	@echo "Running control-plane API in Docker..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

# Docker runtime defaults
WORKER_CONTAINER_NAME ?= control-plane-worker
WORKER_DOCKER_NETWORK ?= host
API_CONTAINER_NAME ?= control-plane-api
API_DOCKER_NETWORK ?= host
