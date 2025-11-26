PY_PACKAGE=cir
APP ?= cir.main:app
# Avoid clashes with agentic (8000), knowledge-flow (8111), and MCP deps (8081/8885/9797)
PORT ?= 8205

include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

.PHONY: install hipporag run test clean-egg

install: dev ## Create venv and install dependencies

hipporag: dev ## Force-install HippoRAG without deps (upstream pin is broken)
	$(UV) pip install --no-deps hipporag==2.0.0a4

run: install ## Start FastAPI with uvicorn
	$(UV) run uvicorn $(APP) --reload --host 0.0.0.0 --port $(PORT)

test: dev ## Run unit tests
	$(UV) run pytest

# Extra clean hook to drop egg-info produced by editable installs
clean: clean-egg

clean-egg:
	rm -rf *.egg-info

# Ensure tooling targets bootstrap the venv first
lint: dev
format: dev
format-fix: dev
code-quality: dev
sast: $(BANDIT_BASELINE_FILE)
detect-secret: $(DETECT_SECRET_BASELINE_FILE)
type-check: $(BASEDPYRIGHT_BASELINE_FILE)

# --------------------------------------------------------------------
# Baseline helpers so code-quality works out of the box
BANDIT_BASELINE_FILE := $(CURDIR)/.baseline/bandit-baseline.json
DETECT_SECRET_BASELINE_FILE := $(CURDIR)/.baseline/detect-secret-baseline.json
BASEDPYRIGHT_BASELINE_FILE := $(CURDIR)/.baseline/basedpyright-baseline.json

code-quality: ensure-baselines

.PHONY: ensure-baselines
ensure-baselines: $(BANDIT_BASELINE_FILE) $(DETECT_SECRET_BASELINE_FILE) $(BASEDPYRIGHT_BASELINE_FILE)

$(BANDIT_BASELINE_FILE):
	mkdir -p $(dir $@)
	$(UV) run bandit -r $(PY_PACKAGE) -s $(BANDIT_IGNORED_RULES) -f json -o $@ || true

$(DETECT_SECRET_BASELINE_FILE):
	mkdir -p $(dir $@)
	cd .. && $(VENV)/bin/detect-secrets scan $(CURDIR) > $@ || true

$(BASEDPYRIGHT_BASELINE_FILE):
	mkdir -p $(dir $@)
	$(UV) run basedpyright --baseline-file $@ --writebaseline || true
