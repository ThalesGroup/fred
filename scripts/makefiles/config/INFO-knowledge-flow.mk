# Project Metadata
PROJECT_NAME        ?= knowledge-flow-backend
PROJECT_SLUG		?= knowledge-flow-backend
VERSION             ?= 0.2
PY_PACKAGE          ?= knowledge_flow_backend

# Docker/Registry
REGISTRY_URL        ?= ghcr.io
REGISTRY_NAMESPACE  ?= thalesgroup/fred-agent
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-prod
DOCKER_CONTEXT      ?= ../..
IMAGE_NAME          ?= knowledge-flow-backend
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

# Runtime
PORT                ?= 8111
ENV_FILE            ?= .venv
LOG_LEVEL           ?= info
PROJECT_ID          ?= 74648
HELM_ARCHIVE        ?= ./$(PROJECT_SLUG)-$(VERSION).tgz

# Config JSON schema
CONFIG_SCHEMA_MODULE ?= knowledge_flow_backend.common.structures
CONFIG_SCHEMA_CLASS  ?= Configuration
