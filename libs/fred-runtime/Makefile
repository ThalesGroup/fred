PROJECT_NAME=fred-runtime
PY_PACKAGE=fred_runtime

include ../../scripts/makefiles/python-vars.mk

include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/python-publish.mk
include ../../scripts/makefiles/alembic.mk
include ../../scripts/makefiles/help.mk

##@ OpenAPI spec

.PHONY: generate-openapi
generate-openapi: dev ## Generate the frontend-facing fred-runtime OpenAPI JSON spec
	@echo "🔧 Generating fred-runtime OpenAPI specification..."
	$(UV) run python scripts/generate_openapi.py
