##@ Tests

# Extra options you can pass to pytest, e.g.:
#   make test PYTEST_OPTS=-v          # one line per test
#   make test PYTEST_OPTS="-vv -rA"    # very verbose + report summary
PYTEST_OPTS ?=

.PHONY: test
test: dev ## Run all tests
	@echo "************ TESTING ************"
	# Ensure uv doesn't warn about foreign active VIRTUAL_ENV
	VIRTUAL_ENV= ${UV} run pytest $(PYTEST_OPTS) -m "not integration" --cov=. --cov-config=.coveragerc --cov-report=html
	@echo "✅ Coverage report: htmlcov/index.html"
	@if [ "${OPEN_COVERAGE}" = "1" ]; then \
		xdg-open htmlcov/index.html || echo "📎 Open manually htmlcov/index.html"; \
	else \
		echo "📎 Set OPEN_COVERAGE=1 to auto-open coverage in a browser"; \
	fi

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
	${UV} run pytest $(PYTEST_OPTS) -v $(subst ::,::,$(TEST))

INTEGRATION_COMPOSE := $(CURDIR)/docker-compose.integration.yml

.PHONY: integration-up
integration-up: ## Start integration test dependencies
	docker compose -f $(INTEGRATION_COMPOSE) up -d

.PHONY: integration-down
integration-down: ## Stop integration test dependencies
	docker compose -f $(INTEGRATION_COMPOSE) down -v

.PHONY: test-integration-only
test-integration-only: dev ## Run integration tests that rely on external services
	${UV} run pytest -m integration

.PHONY: test-integration
test-integration: dev ## Run integration tests that rely on external services and start/stop those services automatically
	@set -e; trap 'docker compose -f $(INTEGRATION_COMPOSE) down -v' EXIT; \
		docker compose -f $(INTEGRATION_COMPOSE) up -d; \
		${UV} run pytest -m integration
