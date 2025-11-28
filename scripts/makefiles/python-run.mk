# Needs:
# - UV
# - PORT
# - ENV_FILE
# - LOG_LEVEL
# And `dev` rule (from `python-deps.mk`)

HOST ?= 0.0.0.0

##@ Run

.PHONY: run-local
run-local: UVICORN_FACTORY ?= ${PY_PACKAGE}.main:create_app
run-local: UVICORN_LOOP ?= asyncio
run-local: ## Run the app assuming dependencies already exist
	$(UV) run uvicorn \
		${UVICORN_FACTORY} \
		--factory \
		--host ${HOST} \
		--port ${PORT} \
		--log-level ${LOG_LEVEL} \
		--loop ${UVICORN_LOOP}


.PHONY: run
run: dev run-local ## run the app, installing dependencies if needed

