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

# Corporate SSL inspection (e.g. Zscaler) — point uv/pip to the system CA bundle.
# SSL_CERT_FILE is used by uv (Rust TLS). PIP_CERT is used by pip only.
# REQUESTS_CA_BUNDLE is intentionally NOT set here: it overrides verify_certs=False in
# opensearchpy's requests session, breaking connections to services with self-signed certs.
export SSL_CERT_FILE ?= $(shell test -f /etc/ssl/certs/ca-certificates.crt && echo /etc/ssl/certs/ca-certificates.crt)
export PIP_CERT ?= $(SSL_CERT_FILE)

# Bypass corporate proxy for local services (Keycloak, Temporal, Postgres, etc.).
# Without this, http_proxy routes localhost requests through the corporate proxy,
# which cannot reach the k3d-mapped ports and breaks OIDC token validation.
export no_proxy ?= localhost,app-keycloak,127.0.0.1,::1
export NO_PROXY ?= $(no_proxy)
