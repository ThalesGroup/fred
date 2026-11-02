# Project Metadata
PROJECT_NAME        ?= knowledge-flow-worker
PROJECT_SLUG		?= knowledge-flow-worker
VERSION             ?= 5.0.0
PY_PACKAGE          ?= knowledge_flow_worker

# Docker/Registry
REGISTRY_URL        ?= ghcr.io
REGISTRY_NAMESPACE  ?= thalesgroup/fred-agent
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-prod
DOCKER_CONTEXT      ?= ../..
IMAGE_NAME          ?= knowledge-flow-worker
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

# Runtime
PORT                ?= 9112
ENV_FILE            ?= .venv
LOG_LEVEL           ?= info
PROJECT_ID          ?= 74648
HELM_ARCHIVE        ?= ./$(PROJECT_SLUG)-$(VERSION).tgz

# Config JSON schema
CONFIG_SCHEMA_MODULE ?= knowledge_flow_worker.common.structures
CONFIG_SCHEMA_CLASS  ?= Configuration
