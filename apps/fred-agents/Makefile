PROJECT_NAME=fred-agents
PY_PACKAGE=fred_agents

include ../../scripts/makefiles/python-vars.mk

include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

.PHONY: run
run: dev ## Run the standalone Fred agents pod locally
	ENV_FILE=$(CURDIR)/config/.env VIRTUAL_ENV= $(UV) run python -m fred_agents

.PHONY: chat
chat: dev ## Open the local interactive chat client for a running agent pod
	ENV_FILE=$(CURDIR)/config/.env VIRTUAL_ENV= $(UV) run fred-agent-chat
