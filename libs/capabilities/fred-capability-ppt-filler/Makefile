PROJECT_NAME=fred-capability-ppt-filler
PY_PACKAGE=fred_capability_ppt_filler

include ../../../scripts/makefiles/python-vars.mk

include ../../../scripts/makefiles/python-deps.mk
include ../../../scripts/makefiles/python-code-quality.mk
include ../../../scripts/makefiles/python-test.mk
include ../../../scripts/makefiles/python-clean.mk
include ../../../scripts/makefiles/python-publish.mk
include ../../../scripts/makefiles/alembic.mk
include ../../../scripts/makefiles/help.mk

##@ Built-in template

.PHONY: builtin-inventory
builtin-inventory: dev ## Regenerate the built-in template's stored analysis after changing the deck or ANALYSIS_VERSION
	$(UV) run python -m $(PY_PACKAGE).builder.builtin

##@ Evaluation

.PHONY: eval
eval: dev ## Opt-in ppt_builder deck-quality evaluation against the real LLM (never part of make test); EVAL_ARGS passes options
	$(UV) run python eval/run_eval.py $(EVAL_ARGS)
