# Project Metadata
PROJECT_NAME        ?= fred-evaluation-backend
PROJECT_SLUG        ?= fred-evaluation-backend
VERSION             ?= 0.1
PY_PACKAGE          ?= fred_evaluation_backend

# Docker/Registry
REGISTRY_URL        ?= ghcr.io
REGISTRY_NAMESPACE  ?= thalesgroup/fred-agent
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-api
DOCKER_CONTEXT      ?= ../..
IMAGE_NAME          ?= fred-evaluation-backend
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

# Runtime
PORT                ?= 8333
ENV_FILE            ?= .venv
LOG_LEVEL           ?= info