# Project Metadata

PROJECT_SLUG		?= frontend
VERSION             ?= 0.1


# Docker/Registry
REGISTRY_URL        ?= ghcr.io
REGISTRY_NAMESPACE  ?= thalesgroup/fred-agent
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-prod
DOCKER_CONTEXT      ?= ..
IMAGE_NAME          ?= frontend
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)

# Runtime
PROJECT_ID          ?= 12345  # Optional if using Helm
HELM_ARCHIVE        ?= ./$(PROJECT_SLUG)-$(VERSION).tgz
