include ../../scripts/makefiles/config/INFO-control-plane.mk

# === Python Utility ===
include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-run.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/python-config-schema.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-security.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/alembic.mk
include ../../scripts/makefiles/help.mk

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

.PHONY: generate-application-catalog
generate-application-catalog: ## Generate the ignored Control Plane application catalog from installed manifests
	$(MAKE) -C ../frontend generate-control-plane-application-catalog

.PHONY: clean-application-catalog
clean-application-catalog:
	rm -f control_plane_backend/applications/catalog.generated.json

clean: clean-application-catalog

# These targets consume application metadata directly or construct the app.
cli run-local run-worker run-worker-prod generate-openapi code-quality test list-tests test-one \
	check-route-security test-integration-only test-integration test-integration-postgres: generate-application-catalog

##@ Dev Helpers

CONTROL_PLANE_BASE_URL ?= http://localhost:8222/control-plane/v1
KEYCLOAK_REALM_URL ?= http://localhost:8080/realms/app
KEYCLOAK_APP_CLIENT_ID ?= app
KEYCLOAK_DEV_USERNAME ?= alice
KEYCLOAK_DEV_PASSWORD ?=
CP_NEW_USER_USERNAME ?= test1
CP_NEW_USER_EMAIL ?= test1@app.com
CP_NEW_USER_PASSWORD ?=

.PHONY: cli
cli: dev ## Open the local interactive control-plane CLI
	ENV_FILE=$(ROOT_DIR)/config/.env VIRTUAL_ENV= $(UV) run fred-control-plane-cli $(ARGS)

BOOTSTRAP_TOKEN_FILE ?= target/bootstrap-token

.PHONY: bootstrap-token
bootstrap-token: ## Create the local root-bootstrap secret (AUTHZ-07). Never overwrites; the app never generates this itself.
	@mkdir -p $(dir $(BOOTSTRAP_TOKEN_FILE))
	@if [ -f $(BOOTSTRAP_TOKEN_FILE) ]; then \
		echo "Already exists: $(BOOTSTRAP_TOKEN_FILE) (not overwritten)"; \
	else \
		umask 077 && openssl rand -hex 32 > $(BOOTSTRAP_TOKEN_FILE).tmp && mv $(BOOTSTRAP_TOKEN_FILE).tmp $(BOOTSTRAP_TOKEN_FILE) && \
		echo "Created: $(BOOTSTRAP_TOKEN_FILE)" || \
		{ echo "Failed to create $(BOOTSTRAP_TOKEN_FILE)" >&2; rm -f $(BOOTSTRAP_TOKEN_FILE).tmp; exit 1; }; \
	fi

BOOTSTRAP_USER ?=
BOOTSTRAP_PASSWORD ?=
KEYCLOAK_REGISTER_URL ?= http://localhost:8080/realms/app/account

.PHONY: bootstrap-local
bootstrap-local: bootstrap-token ## One command for LOCAL-DEVELOPMENT.md steps 1-3 (usage: make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>). Pauses once for the one step that must stay manual: Keycloak self-registration (Fred never creates accounts in Keycloak, on purpose -- see docs/swift/platform/REBAC.md).
	@if [ -z "$(BOOTSTRAP_USER)" ] || [ -z "$(BOOTSTRAP_PASSWORD)" ]; then \
		echo "❌ Usage: make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>"; \
		exit 1; \
	fi
	@if [ -t 0 ]; then \
		echo "ℹ️  Fred never creates Keycloak accounts itself (Keycloak authenticates, Fred/OpenFGA authorizes)."; \
		echo "   Register yourself now at: $(KEYCLOAK_REGISTER_URL)  (username: $(BOOTSTRAP_USER))"; \
		read -p "   Press Enter once you've registered... " _unused; \
	fi
	@TOKEN_RESPONSE=$$(curl -sS -X POST "$(KEYCLOAK_REALM_URL)/protocol/openid-connect/token" \
		-H "Content-Type: application/x-www-form-urlencoded" \
		-d "grant_type=password" \
		-d "client_id=$(KEYCLOAK_APP_CLIENT_ID)" \
		-d "username=$(BOOTSTRAP_USER)" \
		-d "password=$(BOOTSTRAP_PASSWORD)" \
	); \
	TOKEN=$$(printf '%s' "$$TOKEN_RESPONSE" \
		| sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
		| head -n 1); \
	if [ -z "$$TOKEN" ]; then \
		echo "❌ Could not log in as $(BOOTSTRAP_USER) -- did you finish registering at $(KEYCLOAK_REGISTER_URL)?"; \
		echo "   Re-run: make bootstrap-local BOOTSTRAP_USER=$(BOOTSTRAP_USER) BOOTSTRAP_PASSWORD=..."; \
		exit 1; \
	fi; \
	RESPONSE=$$(curl -sS -w '\n%{http_code}' -X POST "$(CONTROL_PLANE_BASE_URL)/bootstrap/platform-admin" \
		-H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" \
		-d "{\"token\": \"$$(cat $(BOOTSTRAP_TOKEN_FILE))\"}"); \
	HTTP_CODE=$$(printf '%s' "$$RESPONSE" | tail -n1); \
	BODY=$$(printf '%s' "$$RESPONSE" | sed '$$d'); \
	if [ "$$HTTP_CODE" = "409" ]; then \
		IS_ADMIN=$$(curl -sS "$(CONTROL_PLANE_BASE_URL)/frontend/bootstrap" -H "Authorization: Bearer $$TOKEN" \
			| $(UV) run python -c 'import sys,json; print(bool(json.load(sys.stdin).get("permissions",{}).get("is_platform_admin")))' 2>/dev/null); \
		if [ "$$IS_ADMIN" = "True" ]; then \
			echo "✓ $(BOOTSTRAP_USER) is already platform_admin (one-shot bootstrap already used)."; \
		else \
			echo "❌ The one-shot bootstrap was already consumed by a DIFFERENT account -- $(BOOTSTRAP_USER) is NOT platform_admin."; \
			echo "   Ask whoever ran it first, or use their account for the rest of this walkthrough."; \
			exit 1; \
		fi; \
	elif [ "$$HTTP_CODE" != "200" ] && [ "$$HTTP_CODE" != "201" ]; then \
		echo "❌ Bootstrap call failed (HTTP $$HTTP_CODE): $$BODY"; \
		exit 1; \
	else \
		echo "✓ $(BOOTSTRAP_USER) is now platform_admin."; \
	fi

.PHONY: activate-all-capabilities
activate-all-capabilities: ## Set every catalog capability (tools + agent templates) to platform-wide default_on -- same effect as Admin > Capabilities > select all (usage: make activate-all-capabilities BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>, must already be platform_admin)
	@if [ -z "$(BOOTSTRAP_USER)" ] || [ -z "$(BOOTSTRAP_PASSWORD)" ]; then \
		echo "❌ Usage: make activate-all-capabilities BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>"; \
		exit 1; \
	fi
	@TOKEN_RESPONSE=$$(curl -sS -X POST "$(KEYCLOAK_REALM_URL)/protocol/openid-connect/token" \
		-H "Content-Type: application/x-www-form-urlencoded" \
		-d "grant_type=password" \
		-d "client_id=$(KEYCLOAK_APP_CLIENT_ID)" \
		-d "username=$(BOOTSTRAP_USER)" \
		-d "password=$(BOOTSTRAP_PASSWORD)" \
	); \
	TOKEN=$$(printf '%s' "$$TOKEN_RESPONSE" \
		| sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
		| head -n 1); \
	if [ -z "$$TOKEN" ]; then \
		echo "❌ Could not log in as $(BOOTSTRAP_USER)."; \
		exit 1; \
	fi; \
	CAP_IDS=$$(curl -sS "$(CONTROL_PLANE_BASE_URL)/admin/capabilities" -H "Authorization: Bearer $$TOKEN" \
		| $(UV) run python -c 'import sys,json; print("\n".join(i["id"] for i in json.load(sys.stdin)["items"]))'); \
	if [ -z "$$CAP_IDS" ]; then \
		echo "❌ No capabilities returned -- is fred-agents reachable? (check its terminal from 'make run')"; \
		exit 1; \
	fi; \
	FAILED=""; \
	for id in $$CAP_IDS; do \
		STATUS=$$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "$(CONTROL_PLANE_BASE_URL)/admin/capabilities/$$id/default-on" \
			-H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" \
			-d '{"default_on": true}'); \
		if [ "$$STATUS" = "200" ] || [ "$$STATUS" = "201" ]; then \
			echo "default-on: $$id"; \
		elif [ "$$STATUS" = "409" ]; then \
			echo "skipped (needs team-specific settings): $$id"; \
		else \
			echo "❌ default-on FAILED (HTTP $$STATUS): $$id"; \
			FAILED="$$FAILED $$id"; \
		fi; \
	done; \
	if [ -n "$$FAILED" ]; then \
		echo "❌ $$(echo $$FAILED | wc -w | tr -d ' ') capabilit(y/ies) failed unexpectedly -- is $(BOOTSTRAP_USER) still platform_admin?"; \
		exit 1; \
	fi; \
	echo "✓ $$(printf '%s\n' "$$CAP_IDS" | wc -l | tr -d ' ') capabilities processed. Any \"skipped\" above needs a value only a team can supply -- grant it to one demo team explicitly instead, see LOCAL-DEVELOPMENT.md."

DEMO_PROVISIONING_FIXTURE_DIR ?= tests/fixtures/import_export/demo_provisioning
DEMO_BUNDLE_FILE ?= target/demo-provisioning-bundle.zip

.PHONY: build-demo-bundle
build-demo-bundle: ## Zip the checked-in demo provisioning fixture (manifest.json + users.json) for upload via Admin > Migration
	@mkdir -p $(dir $(DEMO_BUNDLE_FILE))
	@rm -f $(DEMO_BUNDLE_FILE)
	cd $(DEMO_PROVISIONING_FIXTURE_DIR) && zip -q -X $(abspath $(DEMO_BUNDLE_FILE)) manifest.json users.json
	@echo "Created: $(DEMO_BUNDLE_FILE)"

LOAD_TEST_DIR ?= target/load_test_provisioning
LOAD_TEST_BUNDLE_FILE ?= target/load-test-provisioning-bundle.zip
LOAD_TEST_USERS ?= 3000
LOAD_TEST_TEAMS ?= 100
LOAD_TEST_PREFIX ?= user

.PHONY: build-load-test-bundle
build-load-test-bundle: ## Generate + zip a synthetic N-user/M-team bundle for local OpenFGA scale testing (LOAD_TEST_USERS/LOAD_TEST_TEAMS/LOAD_TEST_PREFIX env vars; not the curated demo fixture). Usernames must already exist in Keycloak, e.g. via fred-deployment-factory's keycloak-add-user.sh --count
	@rm -rf $(LOAD_TEST_DIR)
	$(UV) run python tools/generate_load_test_bundle.py \
		--users $(LOAD_TEST_USERS) --teams $(LOAD_TEST_TEAMS) --prefix $(LOAD_TEST_PREFIX) --out-dir $(LOAD_TEST_DIR)
	@rm -f $(LOAD_TEST_BUNDLE_FILE)
	cd $(LOAD_TEST_DIR) && zip -q -X $(abspath $(LOAD_TEST_BUNDLE_FILE)) manifest.json users.json
	@echo "Created: $(LOAD_TEST_BUNDLE_FILE)"

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
