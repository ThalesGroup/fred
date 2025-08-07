# Project Metadata
PROJECT_NAME        ?= agentic
PROJECT_SLUG        ?= agentic-backend
PY_PACKAGE          ?= app
VERSION             ?= 0.1-dev

# Docker/Registry
REGISTRY_URL        ?= registry.thalesdigital.io
REGISTRY_NAMESPACE  ?= tsn/projects/agentic_app
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-prod
DOCKER_CONTEXT      ?= ..
IMAGE_NAME          ?= $(PROJECT_NAME)
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

# Runtime
PORT                ?= 8000
ENV_FILE            ?= .venv
LOG_LEVEL           ?= info
PROJECT_ID          ?= 12345  # Optional if using Helm
HELM_ARCHIVE        ?= ./$(PROJECT_SLUG)-$(VERSION).tgz
