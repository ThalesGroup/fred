# Needs:
# - PIP
# - TARGET
# - UV

##@ Dependency Management

$(TARGET)/.venv-created:
	@echo "🔧 Creating virtualenv..."
	mkdir -p $(TARGET)
	flock $(TARGET)/.venv.lock sh -c 'test -f $@ || (python3 -m venv $(VENV) && touch $@)'

$(TARGET)/.uv-installed: $(TARGET)/.venv-created
	@echo "📦 Installing uv..."
	flock $(TARGET)/.uv.lock sh -c 'test -f $@ || ($(PIP) install --upgrade pip setuptools wheel && $(PIP) install uv && touch $@)'

$(TARGET)/.compiled: pyproject.toml $(TARGET)/.uv-installed
	flock $(TARGET)/.compiled.lock sh -c '$(UV) sync --extra dev && touch $@'

.PHONY: _ensure-tool-shims
_ensure-tool-shims: $(TARGET)/.compiled
	@# Some processors invoke `pandoc` directly via subprocess. We depend on
	@# `pypandoc-binary`, which bundles pandoc but doesn't put it on PATH.
	@# Create a lightweight shim in the venv so `pandoc` is available when installed.
	@if [ ! -x "$(VENV)/bin/pandoc" ]; then \
		pandoc_path="$$( $(PYTHON) -c "import pypandoc; print(pypandoc.get_pandoc_path())" 2>/dev/null || true )"; \
		if [ -n "$$pandoc_path" ] && [ -x "$$pandoc_path" ]; then \
			ln -sf "$$pandoc_path" "$(VENV)/bin/pandoc"; \
		fi; \
	fi

.PHONY: dev
dev: $(TARGET)/.compiled _ensure-tool-shims ## Install from compiled lock
	@echo "✅ Dependencies installed using uv."


update: $(TARGET)/.uv-installed ## Re-resolve and update all dependencies for the dev environment
	$(UV) sync --extra dev
	touch $(TARGET)/.compiled
