VERSION=0.1.0
PROJECT_NAME=agentic-backend
PY_PACKAGE=app
PROJECT_REGISTRY=registry.thalesdigital.io/tsn/projects/agentic_app
PROJECT_NAME=agentic
IMG=$(PROJECT_REGISTRY)/$(PROJECT_NAME):$(VERSION)

.PHONY: docker-build

docker-build: ## Build the Docker image
	docker build \
		-f ../agentic_backend/dockerfiles/Dockerfile-prod \
		-t $(IMG) \
		../

PORT ?= 8000
include ../scripts/makefiles/python-vars.mk

include ../scripts/makefiles/python-deps.mk
include ../scripts/makefiles/python-run.mk
include ../scripts/makefiles/python-openapi.mk
include ../scripts/makefiles/python-code-quality.mk
include ../scripts/makefiles/python-test.mk
include ../scripts/makefiles/python-clean.mk
include ../scripts/makefiles/help.mk
