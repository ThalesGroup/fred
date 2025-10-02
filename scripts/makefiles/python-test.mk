##@ Tests

.PHONY: test
test: dev ## Run all tests
	@echo "************ TESTING ************"
	${UV} run pytest -m "not integration" --cov=. --cov-config=.coveragerc --cov-report=html
	@echo "✅ Coverage report: htmlcov/index.html"
	@xdg-open htmlcov/index.html || echo "📎 Open manually htmlcov/index.html"

.PHONY: list-tests
list-tests: dev ## List all available test names using pytest
	@echo "************ AVAILABLE TESTS ************"
	${UV} run pytest --collect-only -q | grep -v "<Module"

.PHONY: test-one
test-one: dev ## Run a specific test by setting TEST=...
	@if [ -z "$(TEST)" ]; then \
		echo "❌ Please provide a test path using: make test-one TEST=path::to::test"; \
		exit 1; \
	fi
	${UV} run pytest -v $(subst ::,::,$(TEST))

INTEGRATION_COMPOSE := $(CURDIR)/docker-compose.integration.yml

.PHONY: integration-up
integration-up: ## Start integration test dependencies
	docker compose -f $(INTEGRATION_COMPOSE) up -d

.PHONY: integration-down
integration-down: ## Stop integration test dependencies
	docker compose -f $(INTEGRATION_COMPOSE) down -v

.PHONY: test-integration-only
test-integration-only: export SPICEDB_TEST_ENDPOINT := localhost:60051
test-integration-only: dev ## Run integration tests that rely on external services
	${UV} run pytest -m integration

.PHONY: test-integration
test-integration: export SPICEDB_TEST_ENDPOINT := localhost:60051
test-integration: dev ## Run integration tests that rely on external services and start/stop those services automatically
	@set -e; trap 'docker compose -f $(INTEGRATION_COMPOSE) down -v' EXIT; \
		docker compose -f $(INTEGRATION_COMPOSE) up -d; \
		${UV} run pytest -m integration
