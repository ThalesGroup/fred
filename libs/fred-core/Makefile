VERSION=0.1.0
PROJECT_NAME=fred-core
PY_PACKAGE=fred_core

include ../../scripts/makefiles/python-vars.mk

include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/python-publish.mk
include ../../scripts/makefiles/help.mk

.PHONY: coverage-offline
coverage-offline: dev ## Run the canonical offline coverage report with term-missing output
	@echo "************ OFFLINE COVERAGE ************"
	# Ensure uv doesn't warn about foreign active VIRTUAL_ENV
	# Keep coverage aligned with the default offline test contract.
	VIRTUAL_ENV= ${UV} run pytest $(PYTEST_OPTS) -m "not integration" --disable-socket --allow-unix-socket --cov=fred_core --cov-report=term-missing -q

transform-openfga-schema: ## Transform OpenFga ReBAC schema from a human readable `.fga` in a `.json` readable with code
	fga model transform --file fred_core/security/rebac/schema.fga > fred_core/security/rebac/schema.fga.json
