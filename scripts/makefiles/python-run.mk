# Needs:
# - UV
# - PORT
# - ENV_FILE
# - LOG_LEVEL

# And `dev` rule (from `python-deps.mk`)


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