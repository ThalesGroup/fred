include ../scripts/makefiles/config/INFO-agentic.mk

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

ENV_FILE := $(ROOT_DIR)/config/.env
export ENV_FILE

##@ Run Worker

.PHONY: run-worker
run-worker: dev ## run the Temporal agent worker
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_worker.yaml $(UV) run python -m agentic_backend.main_worker

.PHONY: run-worker-prod
run-worker-prod: dev ## run the Temporal agent worker with production config
	ENV_FILE=$(ROOT_DIR)/config/.env CONFIG_FILE=./config/configuration_prod.yaml $(UV) run python -m agentic_backend.main_worker

.PHONY: temporal-key
temporal-key: dev ## generate a Temporal payload encryption key
	$(UV) run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

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

.PHONY: docker-run
docker-run: ## Run the app in Docker
	docker run -it \
		-p $(PORT):$(PORT) \
		-v $(realpath config/configuration.yaml):/app/configuration.yaml \
		$(IMAGE_FULL) --config-path /app/configuration.yaml
