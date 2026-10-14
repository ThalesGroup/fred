include ../../scripts/makefiles/config/INFO-fred-manager.mk

# === Rust Utility ===
include ../../scripts/makefiles/rust-vars.mk
include ../../scripts/makefiles/rust-deps.mk
include ../../scripts/makefiles/rust-run.mk
include ../../scripts/makefiles/rust-test.mk
include ../../scripts/makefiles/rust-code-quality.mk
include ../../scripts/makefiles/rust-clean.mk
include ../../scripts/makefiles/help.mk

##@ Dev Helpers

FRED_MANAGER_BASE_URL ?= http://localhost:8400/fred-manager/v1
KEYCLOAK_REALM_URL ?= http://localhost:8080/realms/app
KEYCLOAK_APP_CLIENT_ID ?= app

BOOTSTRAP_USER ?=
BOOTSTRAP_PASSWORD ?=
KEYCLOAK_REGISTER_URL ?= http://localhost:8080/realms/app/account

.PHONY: bootstrap-local
bootstrap-local: ## Become the root platform admin with FRED_BOOTSTRAP_TOKEN, given or from config/.env (usage: make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>). Pauses once for Keycloak self-registration.
	@if [ -z "$(BOOTSTRAP_USER)" ] || [ -z "$(BOOTSTRAP_PASSWORD)" ]; then \
		echo "❌ Usage: make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>"; \
		exit 1; \
	fi
	@if [ -t 0 ]; then \
		echo "ℹ️  Bootstrap authenticates an existing Keycloak account; import-provisioning creates bundle identities."; \
		echo "   Register yourself now at: $(KEYCLOAK_REGISTER_URL)  (username: $(BOOTSTRAP_USER))"; \
		read -p "   Press Enter once you've registered... " _unused; \
	fi
	@GIVEN_TOKEN="$$FRED_BOOTSTRAP_TOKEN"; \
	set -a; if [ -f "$(ENV_FILE)" ]; then . "$(ENV_FILE)"; fi; set +a; \
	if [ -n "$$GIVEN_TOKEN" ]; then FRED_BOOTSTRAP_TOKEN="$$GIVEN_TOKEN"; fi; \
	if [ -z "$$FRED_BOOTSTRAP_TOKEN" ]; then \
		echo "❌ Missing FRED_BOOTSTRAP_TOKEN in $(ENV_FILE)"; \
		exit 1; \
	fi; \
	TOKEN_RESPONSE=$$(curl -sS -X POST "$(KEYCLOAK_REALM_URL)/protocol/openid-connect/token" \
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
	RESPONSE=$$(curl -sS -w '\n%{http_code}' -X POST "$(FRED_MANAGER_BASE_URL)/bootstrap/platform-admin" \
		-H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" \
		-d "{\"token\": \"$$FRED_BOOTSTRAP_TOKEN\"}"); \
	HTTP_CODE=$$(printf '%s' "$$RESPONSE" | tail -n1); \
	BODY=$$(printf '%s' "$$RESPONSE" | sed '$$d'); \
	if [ "$$HTTP_CODE" = "409" ]; then \
		IS_ADMIN=$$(curl -sS "$(FRED_MANAGER_BASE_URL)/me" -H "Authorization: Bearer $$TOKEN" \
			| python3 -c 'import sys,json; print("platform_admin" in json.load(sys.stdin).get("platform_roles",[]))' 2>/dev/null); \
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

ORG_NAME ?=
ORG_ADMIN ?=

.PHONY: create-org
create-org: dev ## Create an organization and its first admin (usage: make create-org ORG_NAME=TSN ORG_ADMIN=<keycloak sub>)
	@if [ -z "$(ORG_NAME)" ] || [ -z "$(ORG_ADMIN)" ]; then \
		echo "❌ Usage: make create-org ORG_NAME=<name> ORG_ADMIN=<keycloak sub>"; \
		exit 1; \
	fi
	$(CARGO) run -- create-org "$(ORG_NAME)" "$(ORG_ADMIN)"

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

.PHONY: model check-model
model: ## Generate OpenFGA JSON from the service's direct-role DSL
	python3 tools/model.py
check-model:
	python3 tools/model.py --check
code-quality: check-model

BUNDLE ?=
TOKEN_FILE ?=
export BUNDLE TOKEN_FILE
.PHONY: import-provisioning
import-provisioning: dev ## Import a bundle as platform admin (BUNDLE=<json path> TOKEN_FILE=<bearer file path>); replay is additive
	@test -n "$$BUNDLE" && test -n "$$TOKEN_FILE" || { echo 'Usage: make import-provisioning BUNDLE=<path> TOKEN_FILE=<path>'; exit 1; }
	$(CARGO) run -- import-provisioning "$$BUNDLE" --token-file "$$TOKEN_FILE"
