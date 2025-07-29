VERSION=0.1-dev
PROJECT_REGISTRY=registry.thalesdigital.io/tsn/projects/knowledge_flow_app
PROJECT_NAME=knowledge-flow
PY_PACKAGE=app

IMG=$(PROJECT_REGISTRY)/$(PROJECT_NAME):$(VERSION)
HELM_ARCHIVE=./knowledge_flow_app-0.1.0.tgz
PROJECT_ID="74648"

PORT ?= 8111

include ../scripts/makefiles/python-vars.mk
include ../scripts/makefiles/python-deps.mk
include ../scripts/makefiles/python-run.mk

##@ Other run

.PHONY: run-worker

run-worker: dev ## Run an ingestion worker this requires a temporal daemon
	@echo "🚀 Running the app..."
	PYTHONPATH=. \
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) ${PY_PACKAGE}/main_worker.py --config-path ./config/configuration_worker.yaml

.PHONY: docker-run

docker-run: ## Run the app in Docker
	docker run -it \
		-p $(PORT):$(PORT) \
		-v ~/.kube/:/home/fred-user/.kube/ \
		-v $(realpath app/config/configuration.yaml):/app/configuration.yaml \
		$(IMG) --config-path /app/configuration.yaml


##@ Build

.PHONY: build

build: dev $(TARGET)/.built ## Build current module

$(TARGET)/.built:
	@echo "************ UV BUILD PLACEHOLDER ************"
	touch $@

.PHONY: docker-build

docker-build: ## Build the Docker image
	docker build -t $(IMG) .

.PHONY: helm-package

helm-package: ## Package the Helm chart
	helm package helm-chart/

##@ Image publishing

.PHONY: docker-push

docker-push: ## Push Docker image IMG
	docker push $(IMG)

.PHONY: helm-push

helm-push: ## Push Helm chart to GitLab package registry
	curl --fail-with-body --request POST \
		 --form "chart=@${HELM_ARCHIVE}" \
		 --user ${GITLAB_USER}:${GITLAB_TOKEN} \
		 https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts

include ../scripts/makefiles/python-code-quality.mk
include ../scripts/makefiles/python-test.mk
include ../scripts/makefiles/python-clean.mk
include ../scripts/makefiles/help.mk
