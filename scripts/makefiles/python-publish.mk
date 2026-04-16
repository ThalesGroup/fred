# Publishes a Python package to PyPI using uv.
#
# Requires:
# - UV          (from python-vars.mk)
# - TARGET      (from python-vars.mk)
# - VERSION     (optional; defaults to pyproject.toml [project].version)
# - PYPI_TOKEN  (environment variable — never hardcode)

# Always read VERSION from pyproject.toml to avoid duplication and env overrides.
override VERSION := $(shell $(PYTHON) -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

##@ Publish

.PHONY: build
build: dev ## Build sdist and wheel into target/dist/
	@echo "🔨 Building $(PROJECT_NAME) $(VERSION)..."
	@rm -rf $(TARGET)/dist
	$(UV) build --out-dir $(TARGET)/dist
	@echo "✅ Artifacts in $(TARGET)/dist/"

.PHONY: publish
publish: build ## Build and publish to PyPI (requires PYPI_TOKEN env var)
	@if [ -z "$(PYPI_TOKEN)" ]; then \
		echo "❌ PYPI_TOKEN is not set. Export it before running make publish."; \
		exit 1; \
	fi
	@echo "🚀 Publishing $(PROJECT_NAME) $(VERSION) to PyPI..."
	$(UV) publish --token $(PYPI_TOKEN) $(TARGET)/dist/*
	@echo "✅ Published $(PROJECT_NAME) $(VERSION)"

.PHONY: publish-dry-run
publish-dry-run: build ## Build only — verify artifacts without uploading
	@echo "📦 Dry-run — artifacts ready in $(TARGET)/dist/:"
	@ls -lh $(TARGET)/dist/
