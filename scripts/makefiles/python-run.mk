# Needs:
# - PIP
# - TARGET
# - UV
# - PORT
# - ENV_FILE
# - LOG_LEVEL

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
	$(UV) sync --extra dev
	touch $@

.PHONY: dev
dev: $(TARGET)/.compiled ## Install from compiled lock
	@echo "✅ Dependencies installed using uv."


.PHONY: update
update: $(TARGET)/.uv-installed ## Re-resolve and update all dependencies
	$(UV) sync
	touch $(TARGET)/.compiled

##@ Run

.PHONY: run-local
run-local: UVICORN_FACTORY ?= app.main:create_app
run-local: UVICORN_LOOP ?= asyncio
run-local: ## Run the app assuming dependencies already exist
	$(UV) run uvicorn \
		--factory ${UVICORN_FACTORY} \
		--port ${PORT} \
		--env-file ${ENV_FILE} \
		--log-level ${LOG_LEVEL} \
		--loop ${UVICORN_LOOP} \
		--reload

.PHONY: run
run: dev run-local ## Install dependencies and run the app