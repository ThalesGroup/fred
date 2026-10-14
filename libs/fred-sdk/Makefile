PROJECT_NAME=fred-sdk
PY_PACKAGE=fred_sdk

# The Knowledge Base pod's configuration file, embedded in the knowledge-base chart's schema.
CONFIG_SCHEMA_MODULE := fred_sdk.knowledge_base.configuration
CONFIG_SCHEMA_CLASS  := PodConfiguration

include ../../scripts/makefiles/python-vars.mk

include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/python-publish.mk
include ../../scripts/makefiles/python-config-schema.mk
include ../../scripts/makefiles/help.mk
