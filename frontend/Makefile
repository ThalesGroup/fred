include ../scripts/makefiles/config/INFO-frontend.mk

.DEFAULT_GOAL := help

NODE_VERSION=22.13.0

##@ Build

.PHONY: check-node
check-node: ## Check if Node.js version is at least the required version
	@REQUIRED=$(NODE_VERSION); \
	CURRENT=$$(node -v | sed 's/^v//'); \
	verlte() { [ "$$1" = "$$2" ] && return 0 || [  "$$(printf '%s\n' "$$1" "$$2" | sort -V | head -n1)" = "$$1" ]; }; \
	if ! verlte "$$REQUIRED" "$$CURRENT"; then \
		echo "Node.js v$$REQUIRED or higher is required, but found v$$CURRENT. Please use the correct version."; \
		exit 1; \
	fi


.PHONY: regen-lockfile
regen-lockfile: check-node ## Regenerate package-lock.json inside Docker
	docker run --rm -it -v $(CURDIR):/src -w /src node:22.13.0 bash -c "rm -rf node_modules package-lock.json && npm install"

.PHONY: node_modules
node_modules: check-node package.json
	@if [ -f package-lock.json ]; then \
		npm ci --no-audit --no-fund --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000; \
	else \
		npm install --no-audit --no-fund --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000; \
	fi

.PHONY: build
build: check-node node_modules ## Build the ui using npm run build
	npm run build

.PHONY: helm-package
helm-package: ## Package the Helm chart into a chart archive
	helm package helm-chart/

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

.PHONY: run-docker
run-docker: ## Run frontend in Docker (maps host port 5173 to container port 8080 by default)
	@echo "🚀 Running frontend in Docker..."
	docker run --rm -it \
		--name $(FRONTEND_CONTAINER_NAME) \
		--network $(FRONTEND_DOCKER_NETWORK) \
		-p $(FRONTEND_HOST_PORT):$(FRONTEND_CONTAINER_PORT) \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

##@ Run

.PHONY: run
run: check-node node_modules ## Run frontend locally with split backend ports (8000/8111/8222)
	VITE_BACKEND_URL=http://localhost:8000 \
	VITE_BACKEND_URL_API=http://localhost:8000 \
	VITE_BACKEND_URL_KNOWLEDGE=http://localhost:8111 \
	VITE_BACKEND_URL_CONTROL_PLANE=http://localhost:8222 \
	npm run dev

run-only:
	npm run dev

##@ Dev

.PHONY: format
format: ## Use prettier to format all codebase
	npx prettier . --write

.PHONY: update-agentic-api
update-agentic-api: ## update the generated hooks used in UI based on agentic backend openApi spec
	@echo "🔧 Installing frontend dependencies..."
	npm ci
	@echo "🔧 Generating agentic backend OpenAPI specification..."
	cd ../agentic-backend && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for agentic backend..."
	npx -y @rtk-query/codegen-openapi src/slices/agentic/agenticOpenApiConfig.json

.PHONY: update-knowledge-flow-api
update-knowledge-flow-api: ## update the generated hooks used in UI based on knowledge-flow backend openApi spec
	@echo "🔧 Installing frontend dependencies..."
	npm ci
	@echo "🔧 Generating knowledge-flow backend OpenAPI specification..."
	cd ../knowledge-flow-backend && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for knowledge-flow backend..."
	npx -y @rtk-query/codegen-openapi src/slices/knowledgeFlow/knowledgeFlowOpenApiConfig.json

.PHONY: update-control-plane-api
update-control-plane-api: ## update the generated hooks used in UI based on control-plane backend openApi spec
	@echo "🔧 Generating control-plane backend OpenAPI specification..."
	cd ../control-plane-backend && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for control-plane backend..."
	npx -y @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json

##@ Clean

.PHONY: clean
clean: ## Clean requirements and build files
	rm -rf $(CURDIR)/build
	rm -rf $(CURDIR)/dist
	rm -rf $(CURDIR)/node_modules
	rm -rf node_modules

.PHONY: clean-docker
clean-docker: ## Clean up Docker-related artifacts
	docker rm -f $(FRONTEND_CONTAINER_NAME) || true
	docker image prune -f

.PHONY: full-clean
full-clean: clean clean-docker ## Perform a full cleanup

##@ Image and Helm chart publishing

.PHONY: helm-push
helm-push: ## Push the Helm chart to the project registry
	curl --fail-with-body --request POST \
         --form "chart=@${HELM_ARCHIVE}" \
         --user ${GITLAB_USER}:${GITLAB_TOKEN} \
         https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts


include ../scripts/makefiles/help.mk

# Docker runtime defaults
FRONTEND_CONTAINER_NAME ?= frontend
FRONTEND_DOCKER_NETWORK ?= bridge
FRONTEND_HOST_PORT ?= 5173
FRONTEND_CONTAINER_PORT ?= 8080
