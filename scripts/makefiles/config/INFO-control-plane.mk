# Project Metadata
PROJECT_NAME        ?= control-plane
PROJECT_SLUG        ?= control-plane
VERSION             ?= 0.1

# Docker/Registry
REGISTRY_URL        ?= ghcr.io
REGISTRY_NAMESPACE  ?= thalesgroup/fred-agent
DOCKERFILE_PATH     ?= ./dockerfiles/Dockerfile-prod
DOCKER_CONTEXT      ?= .
IMAGE_NAME          ?= control-plane-backend
IMAGE_TAG           ?= $(VERSION)
IMAGE_FULL          ?= $(REGISTRY_URL)/$(REGISTRY_NAMESPACE)/$(IMAGE_NAME):$(IMAGE_TAG)
