# Project Metadata
PROJECT_NAME        ?= control-plane-backend
PROJECT_SLUG        ?= control-plane-backend
VERSION             ?= 0.1
PY_PACKAGE          ?= control_plane_backend

# Docker/Registry
REGISTRY_URL        ?= ghcr.io
REGISTRY_NAMESPACE  ?= thalesgroup/fred-agent
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-prod
DOCKER_CONTEXT      ?= ..
IMAGE_NAME          ?= control-plane-backend
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

# Runtime
PORT                ?= 8222
ENV_FILE            ?= .venv
LOG_LEVEL           ?= info
PROJECT_ID          ?= 12345
HELM_ARCHIVE        ?= ./$(PROJECT_SLUG)-$(VERSION).tgz
