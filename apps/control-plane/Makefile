include ../../scripts/makefiles/config/INFO-control-plane.mk

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
.PHONY: build-demo-bundle build-demo-zip bundle-demo-zip
build-demo-bundle build-demo-zip bundle-demo-zip: ## Build the Acme/Globex demo provisioning ZIP without running services
	python3 tools/build_demo_bundle.py

.PHONY: test-browser
test-browser: ## Run the real provisioning browser journey and integration regressions (frontend dependencies and Chromium required)
	$(MAKE) test-integration CARGO_TEST_OPTS="--test browser_provisioning"

# Fixed secret belongs only to disposable integration fixtures.
test-integration: export CONTROL_PLANE_TEST_BOOTSTRAP_TOKEN := integration-bootstrap-secret

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
