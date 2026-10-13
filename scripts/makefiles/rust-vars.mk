# Common variables defined for all rust backend related rules
# --------------------------------------------------

TARGET?=$(CURDIR)/target

# Rust binaries path (rustup installs without touching the shell PATH)
CARGO?=$(HOME)/.cargo/bin/cargo

# The Temporal client compiles protobuf definitions at build time.
export PROTOC ?= $(HOME)/bin/tools/protoc/bin/protoc

# Needed env variable to start app
ROOT_DIR := $(realpath $(CURDIR))
export ENV_FILE ?= $(ROOT_DIR)/config/.env

# Corporate SSL inspection (e.g. Zscaler) — point TLS clients to the system CA bundle.
export SSL_CERT_FILE ?= $(shell test -f /etc/ssl/certs/ca-certificates.crt && echo /etc/ssl/certs/ca-certificates.crt)

# Bypass corporate proxy for local services (Keycloak, Temporal, Postgres, etc.).
# Without this, http_proxy routes localhost requests through the corporate proxy,
# which cannot reach the k3d-mapped ports and breaks OIDC token validation.
export no_proxy ?= localhost,app-keycloak,127.0.0.1,::1
export NO_PROXY ?= $(no_proxy)
