PROJECT_NAME=fred-capability-writable-document
PY_PACKAGE=fred_capability_writable_document

include ../../scripts/makefiles/python-vars.mk

include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/python-publish.mk
# This capability ships its own Alembic tree, so it gets the same db-* targets
# and the same single-head check as the three backend trees (#2373).
include ../../scripts/makefiles/alembic.mk
include ../../scripts/makefiles/help.mk
