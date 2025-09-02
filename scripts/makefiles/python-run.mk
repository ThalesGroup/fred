# Needs:
# - UV
# - PORT
# - ENV_FILE
# - LOG_LEVEL
# And `dev` rule (from `python-deps.mk`)

HOST ?= 0.0.0.0

##@ Run

.PHONY: run-local
run-local: UVICORN_FACTORY ?= app.main:create_app
run-local: UVICORN_LOOP ?= asyncio
run-local: ## Run the app assuming dependencies already exist
	$(UV) run uvicorn \
		${UVICORN_FACTORY} \
		--factory \
		--host ${HOST} \
		--port ${PORT} \
		--log-level ${LOG_LEVEL} \
		--loop ${UVICORN_LOOP} \
		--reload

.PHONY: run
run: dev ## Install dependencies and run the app with the dev storages activated (duckDB)
	$(MAKE) run-local 

.PHONY: run-prod

run-prod: dev ## Install dependencies and run the app with the prod storages activated (OpenSearch, MinIO & cie.)
	CONFIG_FILE=$(CONFIG_FILE_PROD) $(MAKE) run-local 