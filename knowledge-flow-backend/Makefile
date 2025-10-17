include ../scripts/makefiles/config/INFO-knowledge-flow.mk

# === Python Utility ===
include ../scripts/makefiles/python-vars.mk
include ../scripts/makefiles/python-deps.mk
include ../scripts/makefiles/python-run.mk
include ../scripts/makefiles/python-openapi.mk
include ../scripts/makefiles/python-code-quality.mk
include ../scripts/makefiles/python-security.mk
include ../scripts/makefiles/python-test.mk
include ../scripts/makefiles/python-clean.mk
include ../scripts/makefiles/help.mk

##@ Run

.PHONY: run-worker
run-worker: dev ## Run an ingestion worker (requires Temporal daemon)
	@echo "🚀 Running the worker..."
	PYTHONPATH=. \
	LOG_LEVEL=$(LOG_LEVEL) \
	ENV_FILE=$(ENV_FILE) \
	$(PYTHON) $(PY_PACKAGE)/main_worker.py --config-path ./config/configuration_worker.yaml

.PHONY: docker-run
docker-run: ## Run the app in Docker
	docker run -it \
		-p $(PORT):$(PORT) \
		-v ~/.kube/:/home/fred-user/.kube/ \
		-v $(realpath app/config/configuration.yaml):/app/configuration.yaml \
		$(IMAGE_FULL) --config-path /app/configuration.yaml

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-push
docker-push: ## Push the Docker image
	docker push $(IMAGE_FULL)

##@ Helm

.PHONY: helm-package
helm-package: ## Package the Helm chart
	helm package helm-chart/

.PHONY: helm-push
helm-push: ## Push Helm chart to GitLab package registry
	curl --fail-with-body --request POST \
		--form "chart=@${HELM_ARCHIVE}" \
		--user ${GITLAB_USER}:${GITLAB_TOKEN} \
		https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts

##@ Build

.PHONY: build
build: dev $(TARGET)/.built ## Build current module

$(TARGET)/.built:
	@echo "************ UV BUILD PLACEHOLDER ************"
	touch $@
