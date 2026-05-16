# Common variables defined for all python backend related rules
# --------------------------------------------------

TARGET?=$(CURDIR)/target

# Python binaries path
VENV?=$(CURDIR)/.venv
PYTHON?=$(VENV)/bin/python
PIP?=$(VENV)/bin/pip
UV?=$(VENV)/bin/uv

# Default uv cache directory inside the project to avoid relying on user-global cache paths
# (which can be restricted on some macOS setups and CI sandboxes).
export UV_CACHE_DIR ?= $(TARGET)/.uv-cache

# Needed env variable to start app
ROOT_DIR := $(realpath $(CURDIR))
export ENV_FILE ?= $(ROOT_DIR)/config/.env
#TO DETELE because of redefined in .env
#export CONFIG_FILE ?= $(ROOT_DIR)/config/configuration.yaml
#export CONFIG_FILE_PROD ?= $(ROOT_DIR)/config/configuration_prod.yaml
#export CONFIG_FILE_ACADEMY ?= $(ROOT_DIR)/config/configuration_academy.yaml
export LOG_LEVEL ?= info
