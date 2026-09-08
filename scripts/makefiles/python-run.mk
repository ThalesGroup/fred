# Needs:
# - UV
# - PORT
# - ENV_FILE
# - LOG_LEVEL
# And `dev` rule (from `python-deps.mk`)

# On macOS, binding to 0.0.0.0 can be blocked by local security tooling.
# Default to loopback on Darwin; keep 0.0.0.0 elsewhere.
UNAME_S := $(shell uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')
HOST ?= $(if $(filter darwin,$(UNAME_S)),127.0.0.1,0.0.0.0)
UVICORN_OPTIONS ?=

# --reload watches the cwd only, so an edit in fred-core/fred-sdk/fred-runtime or
# a capability — all editable installs outside it — silently reloads nothing and
# the app keeps serving stale code. Roots come from [tool.uv.sources] so this
# list cannot drift from the dependency graph.
RELOAD_ROOTS = $(CURDIR) $(abspath $(addprefix $(CURDIR)/,$(shell awk '/^\[tool\.uv\.sources\]/{s=1;next} /^\[/{s=0} s' $(CURDIR)/pyproject.toml | sed -n 's/.*path *= *"\([^"]*\)".*/\1/p')))
# The package, never the root: a root also holds .venv/ and target/, gigabytes
# watchfiles would walk on every start.
RELOAD_DIRS = $(filter-out %/tests,$(patsubst %/,%,$(dir $(wildcard $(addsuffix /*/__init__.py,$(RELOAD_ROOTS))))))
RELOAD_OPTIONS = --reload $(foreach d,$(RELOAD_DIRS) $(wildcard $(CURDIR)/config),--reload-dir $(d)) --reload-include '*.yaml'

##@ Run

.PHONY: run-local
run-local: UVICORN_FACTORY ?= ${PY_PACKAGE}.main:create_app
run-local: UVICORN_LOOP ?= auto
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
rrun: UVICORN_OPTIONS = $(RELOAD_OPTIONS)
rrun: run ## run the app with uvicorn reloader

.PHONY: rrun-prod
rrun-prod: UVICORN_OPTIONS = $(RELOAD_OPTIONS)
rrun-prod: run-prod ## run the app with uvicorn reloader in production mode

.PHONY: run-prod-uv-workers
run-prod-uv-workers: UVICORN_OPTIONS = --workers 4
run-prod-uv-workers: run-prod ## run the app in production mode with multiple uvicorn workers (to simulate a k8s setup with replicas easily)
