##@ Config JSON Schema

_SCHEMA_MK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
_GEN_SCHEMA_SCRIPT  := $(_SCHEMA_MK_DIR)/../generate_config_schema.py
_CHECK_CONFIG_SCRIPT := $(_SCHEMA_MK_DIR)/../check_config_files.py

SCHEMA_DIR  := $(ROOT_DIR)/config/schema
SCHEMA_FILE := $(SCHEMA_DIR)/configuration.schema.json

_SCHEMA_QUALIFIED := $(CONFIG_SCHEMA_MODULE).$(CONFIG_SCHEMA_CLASS)

.PHONY: generate-config-schema
generate-config-schema: dev ## Generate JSON schemas from Pydantic config models
	@mkdir -p $(SCHEMA_DIR)
	$(PYTHON) $(_GEN_SCHEMA_SCRIPT) $(_SCHEMA_QUALIFIED) $(SCHEMA_FILE)

_DRIFT_TMP := /tmp/schema-drift-check/$(PROJECT_NAME)

.PHONY: check-config-schema-drift
check-config-schema-drift: dev ## Fail if committed schemas differ from freshly generated ones
	@mkdir -p $(_DRIFT_TMP)
	@$(PYTHON) $(_GEN_SCHEMA_SCRIPT) $(_SCHEMA_QUALIFIED) $(_DRIFT_TMP)/configuration.schema.json
	@diff $(SCHEMA_FILE) $(_DRIFT_TMP)/configuration.schema.json \
		|| (echo "ERROR: $(SCHEMA_FILE) is out of date. Run 'make generate-config-schema' and commit the result." && exit 1)
	@echo "Schema drift check passed for $(notdir $(SCHEMA_FILE))"

.PHONY: check-config-files
check-config-files: dev ## Validate all config/*.yaml files against their JSON schemas (strict: no extra keys)
	$(UV) run $(_CHECK_CONFIG_SCRIPT) $(SCHEMA_FILE) $(ROOT_DIR)/config
