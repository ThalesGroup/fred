##@ OpenAPI spec

_OPENAPI_MK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: generate-openapi
generate-openapi: dev ## Generate OpenAPI JSON specification without starting the server
	@echo "🔧 Generating OpenAPI specification..."
	$(PYTHON) $(_OPENAPI_MK_DIR)/../generate_openapi.py $(PY_PACKAGE)
