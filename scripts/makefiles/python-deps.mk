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
	flock $(TARGET)/.compiled.lock sh -c 'test -f $@ || ($(UV) sync --extra dev && touch $@)'

.PHONY: dev
dev: $(TARGET)/.compiled ## Install from compiled lock
	@echo "✅ Dependencies installed using uv."


.PHONY: update
update: $(TARGET)/.uv-installed ## Re-resolve and update all dependencies
	$(UV) sync
	touch $(TARGET)/.compiled
