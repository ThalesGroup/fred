##@ Helm Chart Schema

_CHART_SCHEMA_MK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
_GEN_CHART_SCHEMA_SCRIPT   := $(_CHART_SCHEMA_MK_DIR)/../generate_chart_schema.py
_CHECK_CHART_VALUES_SCRIPT := $(_CHART_SCHEMA_MK_DIR)/../check_chart_values.py

_CHART_REPO_ROOT   := $(abspath $(_CHART_SCHEMA_MK_DIR)/../..)
_CHART_SCHEMA_FILE := $(_CHART_REPO_ROOT)/deploy/charts/fred/values.schema.json
_CHART_VALUES_FILE := $(_CHART_REPO_ROOT)/deploy/charts/fred/values.yaml

_FA_SCHEMA  := $(_CHART_REPO_ROOT)/apps/fred-agents/config/schema/configuration.schema.json
_KF_SCHEMA  := $(_CHART_REPO_ROOT)/apps/knowledge-flow-backend/config/schema/configuration.schema.json
_CP_SCHEMA  := $(_CHART_REPO_ROOT)/apps/control-plane-backend/config/schema/configuration.schema.json

_ALL_BACKEND_SCHEMAS_PRESENT = \
	$(if $(and $(wildcard $(_FA_SCHEMA)),$(wildcard $(_KF_SCHEMA)),$(wildcard $(_CP_SCHEMA))),yes,)

include $(_CHART_SCHEMA_MK_DIR)/scripts-uv.mk

.PHONY: generate-chart-schema
generate-chart-schema: $(SCRIPTS_UV_READY) ## Regenerate deploy/charts/fred/values.schema.json from all backend config schemas
	$(if $(_ALL_BACKEND_SCHEMAS_PRESENT), \
		$(SCRIPTS_UV) run $(_GEN_CHART_SCHEMA_SCRIPT) \
			--fred-agents    "$(_FA_SCHEMA)" \
			--knowledge-flow "$(_KF_SCHEMA)" \
			--control-plane  "$(_CP_SCHEMA)" \
			--output         "$(_CHART_SCHEMA_FILE)", \
		echo "Skipping chart schema: not all backend schemas are present yet.")

_CHART_DRIFT_TMP := /tmp/schema-drift-check/chart-values

.PHONY: check-chart-schema-drift
check-chart-schema-drift: $(SCRIPTS_UV_READY) ## Fail if values.schema.json differs from freshly generated one
	$(if $(_ALL_BACKEND_SCHEMAS_PRESENT), \
		mkdir -p $(_CHART_DRIFT_TMP) && \
		$(SCRIPTS_UV) run $(_GEN_CHART_SCHEMA_SCRIPT) \
			--fred-agents    "$(_FA_SCHEMA)" \
			--knowledge-flow "$(_KF_SCHEMA)" \
			--control-plane  "$(_CP_SCHEMA)" \
			--output         "$(_CHART_DRIFT_TMP)/values.schema.json" && \
		(diff "$(_CHART_SCHEMA_FILE)" "$(_CHART_DRIFT_TMP)/values.schema.json" \
			|| (echo "ERROR: $(_CHART_SCHEMA_FILE) is out of date. Run 'make generate-chart-schema' and commit the result." && exit 1)) && \
		echo "Chart schema drift check passed.", \
		echo "Skipping chart schema drift check: not all backend schemas are present.")

.PHONY: check-chart-values
check-chart-values: $(SCRIPTS_UV_READY) ## Validate deploy/charts/fred/values.yaml against the generated Helm values schema
	$(if $(_ALL_BACKEND_SCHEMAS_PRESENT), \
		$(SCRIPTS_UV) run $(_CHECK_CHART_VALUES_SCRIPT) "$(_CHART_SCHEMA_FILE)" "$(_CHART_VALUES_FILE)", \
		echo "Skipping chart values check: not all backend schemas are present.")
