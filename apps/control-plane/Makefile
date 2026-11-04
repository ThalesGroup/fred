include ../../scripts/makefiles/config/INFO-control-plane.mk

# Tests exercise the real bootstrap, including the deployment-owned extension.
INTEGRATION_POSTGRES_IMAGE ?= pgvector/pgvector:pg15

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

BUNDLE ?=
TOKEN_FILE ?=
export BUNDLE TOKEN_FILE
.PHONY: import-provisioning
import-provisioning: dev ## Import a bundle as platform owner (BUNDLE=<zip path> TOKEN_FILE=<bearer file path>); replay is additive
	@test -n "$$BUNDLE" && test -n "$$TOKEN_FILE" || { echo 'Usage: make import-provisioning BUNDLE=<path> TOKEN_FILE=<path>'; exit 1; }
	$(CARGO) run -- import-provisioning "$$BUNDLE" --token-file "$$TOKEN_FILE"

DEMO_PROVISIONING_FIXTURE_DIR ?= tests/fixtures/import_export/demo_provisioning
DEMO_BUNDLE_FILE ?= target/demo-provisioning-bundle.zip
export DEMO_PROVISIONING_FIXTURE_DIR DEMO_BUNDLE_FILE
.PHONY: bundle-demo
bundle-demo: ## Build the Acme/Globex demo provisioning ZIP without running services
	python3 tools/build_provisioning_bundle.py "$$DEMO_PROVISIONING_FIXTURE_DIR" "$$DEMO_BUNDLE_FILE"

MIGRATION_BUNDLE_FILE ?= target/nova-migration-bundle.zip
export MIGRATION_BUNDLE_FILE
.PHONY: bundle-migration
bundle-migration: ## Build only the Nova coexistence provisioning ZIP; no services or import
	python3 tools/build_provisioning_bundle.py tests/fixtures/import_export/nova_migration "$$MIGRATION_BUNDLE_FILE"

.PHONY: test-browser
test-browser: ## Run the real provisioning browser journey and integration regressions (frontend dependencies and Chromium required)
	$(MAKE) test-integration CARGO_TEST_OPTS="--test browser_provisioning"

# Fixed secrets belong only to disposable integration fixtures.
test-integration: export CONTROL_PLANE_TEST_BOOTSTRAP_TOKEN := integration-bootstrap-secret
test-integration: export FRED_TEST_INFERENCE_CREDENTIAL := synthetic-inference-key

LIFECYCLE_TEMPORAL_IMAGE ?= mirror.gcr.io/temporalio/admin-tools:1.28
.PHONY: test-lifecycle-temporal
test-lifecycle-temporal: dev ## API/worker restart and history replay on disposable SQL and Temporal
	@set -e; pg=fred-lifecycle-pg-$$$$; temporal=fred-lifecycle-temporal-$$$$; \
	trap 'docker rm -f $$pg $$temporal >/dev/null 2>&1 || true' EXIT; \
	docker run -d --name $$pg -e POSTGRES_PASSWORD=it -p 127.0.0.1::5432 $(INTEGRATION_POSTGRES_IMAGE) >/dev/null; \
	docker run -d --name $$temporal -p 127.0.0.1::7233 --entrypoint temporal $(LIFECYCLE_TEMPORAL_IMAGE) server start-dev --ip 0.0.0.0 --headless >/dev/null; \
	pg_addr=$$(docker port $$pg 5432/tcp | head -n1); temporal_addr=$$(docker port $$temporal 7233/tcp | head -n1); \
	ready=false; for attempt in $$(seq 1 60); do \
		if docker exec $$pg psql -U postgres -h 127.0.0.1 -c 'select 1' >/dev/null 2>&1 && docker exec $$temporal temporal operator cluster health >/dev/null 2>&1; then ready=true; break; fi; \
		sleep 1; \
	done; test "$$ready" = true; \
	CONTROL_PLANE_IT_POSTGRES=postgres://postgres:it@$$pg_addr CONTROL_PLANE_IT_TEMPORAL=$$temporal_addr \
	$(CARGO) test --test lifecycle_temporal -- --ignored

.PHONY: generate-config-schema
generate-config-schema: ## Generate the manager configuration schema without starting services
	@mkdir -p config/schema
	@set -e; tmp=$$(mktemp config/schema/configuration.schema.json.XXXXXX); \
	trap 'rm -f "$$tmp"' EXIT; \
	$(CARGO) run --quiet --locked -- generate-config-schema > "$$tmp"; \
	mv "$$tmp" config/schema/configuration.schema.json

# The real processing journey is opt-in; its subprocess owns the worker venv.
ifneq ($(origin CONTROL_PLANE_IT_PROCESSING),undefined)
test-integration: prepare-processing-worker
endif

.PHONY: prepare-processing-worker
prepare-processing-worker: ## Prepare the Python worker used by document-processing integration tests
	$(MAKE) -C ../knowledge-flow-worker dev

# The embedded runtime is part of this component's supported execution path.
.PHONY: test-rust-agent code-quality-rust-agent
test: test-rust-agent
test-rust-agent: dev
	$(CARGO) test --locked -p fred-rust-agent --lib

code-quality: code-quality-rust-agent
code-quality-rust-agent: dev
	$(CARGO) fmt -p fred-rust-agent --check
	$(CARGO) clippy --locked -p fred-rust-agent --all-targets -- -D warnings
