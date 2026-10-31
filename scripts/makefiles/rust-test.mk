##@ Tests

# Extra options you can pass to cargo test, e.g.:
#   make test CARGO_TEST_OPTS="-- --nocapture"   # show test output
CARGO_TEST_OPTS ?=

.PHONY: test
test: dev ## Run default/offline tests
	@echo "************ TESTING ************"
	# Offline unit tests only (no Keycloak/Temporal/Postgres calls).
	$(CARGO) test $(CARGO_TEST_OPTS)

.PHONY: list-tests
list-tests: dev ## List all available test names using cargo
	@echo "************ AVAILABLE TESTS ************"
	$(CARGO) test -- --list --format terse 2>/dev/null | grep ': test$$'

.PHONY: test-one
test-one: dev ## Run a specific test by setting TEST=...
	@if [ -z "$(TEST)" ]; then \
		echo "❌ Please provide a test name using: make test-one TEST=module::tests::name"; \
		exit 1; \
	fi
	$(CARGO) test $(CARGO_TEST_OPTS) $(TEST) -- --exact

INTEGRATION_POSTGRES_IMAGE ?= mirror.gcr.io/postgres:15.12-alpine3.20

.PHONY: test-integration
test-integration: dev ## Run integration tests against a throwaway Postgres container, removed afterwards
	@set -e; pg=$(PROJECT_SLUG)-it-pg-$$$$; \
	trap 'docker rm -f $$pg >/dev/null 2>&1 || true' EXIT; \
	docker run -d --name $$pg -e POSTGRES_PASSWORD=it -p 127.0.0.1::5432 $(INTEGRATION_POSTGRES_IMAGE) >/dev/null; \
	pg_addr=$$(docker port $$pg 5432/tcp | head -n1); \
	until docker exec $$pg psql -U postgres -h 127.0.0.1 -c 'select 1' >/dev/null 2>&1; do sleep 1; done; \
	echo "************ INTEGRATION TESTING ************"; \
	CONTROL_PLANE_IT_POSTGRES=postgres://postgres:it@$$pg_addr \
	$(CARGO) test $(CARGO_TEST_OPTS) --test integration -- --ignored
