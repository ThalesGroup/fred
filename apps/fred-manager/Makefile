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

.PHONY: generate-openapi
generate-openapi: ## Generate OpenAPI JSON without configuration or running services
	@set -e; tmp=$$(mktemp openapi.json.XXXXXX); \
	trap 'rm -f "$$tmp"' EXIT; \
	$(CARGO) run --quiet --locked -- generate-openapi > "$$tmp"; \
	mv "$$tmp" openapi.json

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
import-provisioning: dev ## Import a bundle as platform admin (BUNDLE=<zip path> TOKEN_FILE=<bearer file path>); replay is additive
	@test -n "$$BUNDLE" && test -n "$$TOKEN_FILE" || { echo 'Usage: make import-provisioning BUNDLE=<path> TOKEN_FILE=<path>'; exit 1; }
	$(CARGO) run -- import-provisioning "$$BUNDLE" --token-file "$$TOKEN_FILE"

DEMO_PROVISIONING_FIXTURE_DIR ?= tests/fixtures/import_export/demo_provisioning
DEMO_BUNDLE_FILE ?= target/demo-provisioning-bundle.zip
export DEMO_PROVISIONING_FIXTURE_DIR DEMO_BUNDLE_FILE
.PHONY: build-demo-bundle
build-demo-bundle: ## Build the demo provisioning ZIP without running services
	python3 tools/build_demo_bundle.py

.PHONY: test-browser
test-browser: ## Run the real provisioning browser journey and integration regressions (frontend dependencies and Chromium required)
	$(MAKE) test-integration CARGO_TEST_OPTS="--test browser_provisioning"

# Fixed secret belongs only to disposable integration fixtures.
test-integration: export FRED_MANAGER_TEST_BOOTSTRAP_TOKEN := integration-bootstrap-secret
