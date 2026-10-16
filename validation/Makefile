# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

include ../scripts/makefiles/help.mk

##@ Validation
#
# Black-box validation of a RUNNING Fred platform (control-plane, frontend,
# runtime, knowledge-flow-backend) plus its Docker/k3d infra. `validation/` is
# not a deployable app (no Docker image, needs live infra, not part of the
# offline `make code-quality`/`make test` sweeps) - it is invoked standalone,
# same as `apps/*` are via `make -C <dir> ...`, but from its own top-level
# Makefile instead of being folded into the root `CODE_QUALITY_DIRS`/`TEST_DIRS`
# loops. See README.md for the full local-stack sequence before running this.

VALIDATION_VENV ?= .venv
PYTHON_BIN      ?= python3

# Shared Fred libraries now live as repo-sibling directories (validation/ moved
# into the `fred` monorepo itself - no more cross-repo env-var indirection needed
# to locate them).
FRED_POD_SRC     ?= ../libs/fred-pod
FRED_CORE_SRC    ?= ../libs/fred-core
FRED_SDK_SRC     ?= ../libs/fred-sdk
FRED_RUNTIME_SRC ?= ../libs/fred-runtime

# These three apps still need to be started manually (see README.md) - moving
# validation/ into the monorepo does not change that, only the file paths.
FRED_CONTROL_PLANE_URL   ?= http://localhost:8222/control-plane/v1
FRED_RUNTIME_PUBLIC_BASE ?= http://localhost:8000
FRED_KNOWLEDGE_FLOW_URL  ?= http://localhost:8111/knowledge-flow/v1
FRED_REALM_URL           ?= http://localhost:8080/realms/app

VALIDATION_REPORT    ?= report.md
VALIDATION_JUNIT_XML ?= report.xml
VALIDATION_ARGS      ?=

.PHONY: integration-test-docker integration-test-k3d
# Select a complete profile even after another profile's URLs were exported.
# Explicit command-line FRED_* assignments still take precedence.
integration-test-docker: FRED_REALM_URL = http://localhost:8080/realms/app
integration-test-docker: FRED_CONTROL_PLANE_URL = http://localhost:8222/control-plane/v1
integration-test-docker: FRED_KNOWLEDGE_FLOW_URL = http://localhost:8111/knowledge-flow/v1
integration-test-docker: FRED_RUNTIME_PUBLIC_BASE = http://localhost:8000
integration-test-k3d: FRED_REALM_URL = http://keycloak:8080/realms/app
integration-test-k3d: FRED_CONTROL_PLANE_URL = http://localhost:8088/control-plane/v1
integration-test-k3d: FRED_KNOWLEDGE_FLOW_URL = http://localhost:8088/knowledge-flow/v1
integration-test-k3d: FRED_RUNTIME_PUBLIC_BASE = http://localhost:8088

integration-test-docker: ## Validate running Docker-backed services and local Fred apps through direct ports
integration-test-k3d: ## Validate running k3d apps through localhost:8088 and the trusted Keycloak issuer
integration-test-docker integration-test-k3d:
	$(MAKE) validation-report \
	  FRED_REALM_URL="$(FRED_REALM_URL)" \
	  FRED_CONTROL_PLANE_URL="$(FRED_CONTROL_PLANE_URL)" \
	  FRED_KNOWLEDGE_FLOW_URL="$(FRED_KNOWLEDGE_FLOW_URL)" \
	  FRED_RUNTIME_PUBLIC_BASE="$(FRED_RUNTIME_PUBLIC_BASE)"

.PHONY: validation-report
validation-report: ## Run the full live validation suite (no -x) and write a short claims-grouped Markdown report - requires infra + running apps, see README.md
	@test -x $(VALIDATION_VENV)/bin/python || { \
	  echo "▶ creating venv $(VALIDATION_VENV) (python3 -m venv)"; \
	  $(PYTHON_BIN) -m venv $(VALIDATION_VENV) && \
	  $(VALIDATION_VENV)/bin/pip install -q --upgrade pip; \
	}
	@echo "▶ installing deps (shared Fred libs editable + this validation package)"
	@$(VALIDATION_VENV)/bin/pip install -q -e $(FRED_POD_SRC) -e $(FRED_CORE_SRC) -e $(FRED_SDK_SRC) -e $(FRED_RUNTIME_SRC) -e .
	@echo "▶ running the full suite (no -x, so one failure doesn't hide the rest)"
	@set +e; \
	  FRED_REALM_URL="$(FRED_REALM_URL)" \
	  FRED_CONTROL_PLANE_URL="$(FRED_CONTROL_PLANE_URL)" \
	  FRED_RUNTIME_PUBLIC_BASE="$(FRED_RUNTIME_PUBLIC_BASE)" \
	  FRED_KNOWLEDGE_FLOW_URL="$(FRED_KNOWLEDGE_FLOW_URL)" \
	  $(VALIDATION_VENV)/bin/pytest $(VALIDATION_ARGS) --junitxml=$(VALIDATION_JUNIT_XML); \
	  rc=$$?; \
	  $(VALIDATION_VENV)/bin/python generate_report.py $(VALIDATION_JUNIT_XML) | tee $(VALIDATION_REPORT); \
	  echo ""; \
	  echo "✓ Report written to $(VALIDATION_REPORT)"; \
	  exit $$rc

.PHONY: validation-unit-tests
validation-unit-tests: ## Offline tests for the validation harness, document probes and factory configuration - no running stack required
	@test -x $(VALIDATION_VENV)/bin/python || { \
	  echo "▶ creating venv $(VALIDATION_VENV) (python3 -m venv)"; \
	  $(PYTHON_BIN) -m venv $(VALIDATION_VENV) && \
	  $(VALIDATION_VENV)/bin/pip install -q --upgrade pip; \
	}
	@echo "▶ installing deps (shared Fred libs editable + this validation package)"
	@$(VALIDATION_VENV)/bin/pip install -q -e $(FRED_POD_SRC) -e $(FRED_CORE_SRC) -e $(FRED_SDK_SRC) -e $(FRED_RUNTIME_SRC) -e .
	@echo "▶ running offline unit tests (no live stack)"
	$(VALIDATION_VENV)/bin/pytest tests -q
