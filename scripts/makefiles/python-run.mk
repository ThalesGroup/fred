# Needs:
# - UV
# - PORT
# - ENV_FILE
# - LOG_LEVEL
# And `dev` rule (from `python-deps.mk`)

HOST ?= 0.0.0.0
UVICORN_OPTIONS ?=

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
		--loop ${UVICORN_LOOP} \
		${UVICORN_OPTIONS}


.PHONY: run
run: dev run-local ## run the app, installing dependencies if needed

.PHONY: run-prod
run-prod: export CONFIG_FILE = ./config/configuration_prod.yaml
run-prod: run ## run the app with prod like configuration

.PHONY: rrun
rrun: UVICORN_OPTIONS = --reload
rrun: run ## run the app with uvicorn reloader

.PHONY: rrun-prod
rrun-prod: UVICORN_OPTIONS = --reload
rrun-prod: run-prod ## run the app with uvicorn reloader in production mode

.PHONY: run-prod-uv-workers
run-prod-uv-workers: UVICORN_OPTIONS = --workers 4
run-prod-uv-workers: run-prod ## run the app in production mode with multiple uvicorn workers (to simulate a k8s setup with replicas easily)