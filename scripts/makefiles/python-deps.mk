# Needs:
# - PIP
# - TARGET
# - UV

##@ Dependency Management

define run_with_file_lock
	if command -v flock >/dev/null 2>&1; then \
		flock $(1) sh -c $(2); \
	elif command -v lockf >/dev/null 2>&1; then \
		lockf $(1) sh -c $(2); \
	else \
		echo "WARNING: neither flock nor lockf found; continuing without a file lock."; \
		sh -c $(2); \
	fi
endef

$(TARGET)/.venv-created:
	@echo "🔧 Creating virtualenv..."
	mkdir -p $(TARGET)
	$(call run_with_file_lock,$(TARGET)/.venv.lock,'test -f $@ || (python3 -m venv $(VENV) && touch $@)')

$(TARGET)/.uv-installed: $(TARGET)/.venv-created
	@echo "📦 Installing uv..."
	$(call run_with_file_lock,$(TARGET)/.uv.lock,'test -f $@ || ($(PIP) install --upgrade pip setuptools wheel && $(PIP) install uv && touch $@)')

$(TARGET)/.compiled: pyproject.toml $(TARGET)/.uv-installed
	$(call run_with_file_lock,$(TARGET)/.compiled.lock,'test -f $@ || ($(UV) sync --extra dev && touch $@)')

.PHONY: dev
dev: $(TARGET)/.compiled ## Install from compiled lock
	@echo "✅ Dependencies installed using uv."


.PHONY: update
update: $(TARGET)/.uv-installed ## Re-resolve and update all dependencies
	$(UV) sync
	touch $(TARGET)/.compiled
