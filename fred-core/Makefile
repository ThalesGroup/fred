VERSION=0.1.0
PROJECT_NAME=fred-core
PY_PACKAGE=fred_core

include ../scripts/makefiles/python-vars.mk

include ../scripts/makefiles/python-deps.mk
include ../scripts/makefiles/python-code-quality.mk
include ../scripts/makefiles/python-test.mk
include ../scripts/makefiles/python-clean.mk
include ../scripts/makefiles/help.mk

transform-openfga-schema: # Transform OpenFga ReBAC schema from a human readable `.fga` in a `.json` readable with code
	fga model transform --file fred_core/security/rebac/schema.fga > fred_core/security/rebac/schema.fga.json
