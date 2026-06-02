PROJECT_NAME=fred-agents
PY_PACKAGE=fred_agents

PORT ?= 8000

include ../../scripts/makefiles/python-vars.mk

include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-run.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

.PHONY: cli
cli: dev ## Open the interactive CLI for a running agent pod
	ENV_FILE=$(CURDIR)/config/.env VIRTUAL_ENV= $(UV) run fred-agents-cli
