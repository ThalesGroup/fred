##@ Tests

# Extra options you can pass to cargo test, e.g.:
#   make test CARGO_TEST_OPTS="-- --nocapture"   # show test output
CARGO_TEST_OPTS ?=

.PHONY: test
test: dev ## Run default/offline tests
	@echo "************ TESTING ************"
	# Offline unit tests only (no Keycloak/Temporal/OpenFGA/Postgres calls).
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
