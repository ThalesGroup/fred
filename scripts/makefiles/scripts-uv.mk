# Shared uv bootstrap for standalone scripts under scripts/*.py.
#
# These scripts declare their dependencies via PEP 723 inline metadata (the
# `# /// script` block), which only `uv run` parses — plain `python3` ignores
# it. We can't assume contributors have a global uv (in this repo it's
# normally pip-installed into each app's own .venv), so this bootstraps one
# shared venv for all repo-root scripts and exposes it as $(SCRIPTS_UV).
#
# Usage: include this file, then invoke scripts as:
#   my-target: $(SCRIPTS_UV_READY)
#   	$(SCRIPTS_UV) run $(SOME_SCRIPT_MK_DIR)/../some_script.py ...

_SCRIPTS_UV_MK_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
_SCRIPTS_REPO_ROOT  := $(abspath $(_SCRIPTS_UV_MK_DIR)/../..)

SCRIPTS_TARGET   := $(_SCRIPTS_REPO_ROOT)/target/scripts-venv
SCRIPTS_VENV     := $(SCRIPTS_TARGET)/venv
SCRIPTS_PIP      := $(SCRIPTS_VENV)/bin/pip
SCRIPTS_UV       := $(SCRIPTS_VENV)/bin/uv
SCRIPTS_UV_READY := $(SCRIPTS_TARGET)/.uv-installed

TARGET := $(SCRIPTS_TARGET)
VENV   := $(SCRIPTS_VENV)
PIP    := $(SCRIPTS_PIP)
include $(_SCRIPTS_UV_MK_DIR)/python-venv-bootstrap.mk
