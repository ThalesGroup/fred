# Needs:
# - PIP
# - TARGET
# - UV

.DELETE_ON_ERROR:

##@ Dependency Management

$(TARGET)/.venv-created:
	@echo "🔧 Creating virtualenv..."
	mkdir -p $(TARGET)
	python3 -m venv $(VENV)
	touch $@

$(TARGET)/.uv-installed: $(TARGET)/.venv-created
	@echo "📦 Installing uv..."
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install uv
	touch $@

$(TARGET)/.compiled: pyproject.toml $(TARGET)/.uv-installed
	@if [ ! -x "$(UV)" ]; then \
		echo "⚠️  uv binary missing, reinstalling..."; \
		rm -f $(TARGET)/.uv-installed; \
		$(MAKE) $(TARGET)/.uv-installed; \
	fi
	@echo "📦 Syncing dependencies..."
	$(UV) sync --extra dev
	touch $@

.PHONY: dev
dev: $(TARGET)/.compiled ## Install from compiled lock
	@echo "✅ Dependencies installed using uv."


.PHONY: update
update: $(TARGET)/.uv-installed ## Re-resolve and update all dependencies
	$(UV) sync
	touch $(TARGET)/.compiled
