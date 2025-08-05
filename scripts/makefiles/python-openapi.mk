##@ OpenAPI spec

.PHONY: generate-openapi
generate-openapi: dev ## Generate OpenAPI JSON specification without starting the server
	@echo "🔧 Generating OpenAPI specification..."
	$(PYTHON) ../scripts/generate_openapi.py
