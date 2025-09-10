##@ Tests

.PHONY: test
test: dev ## Run all tests
	@echo "************ TESTING ************"
	${UV} run pytest --cov=. --cov-config=.coveragerc --cov-report=html
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
