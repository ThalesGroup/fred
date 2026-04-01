CODE_QUALITY_DIRS := fred-core agentic-backend knowledge-flow-backend control-plane-backend
TEST_DIRS := agentic-backend knowledge-flow-backend control-plane-backend
DOCKER_BUILD_DIRS := agentic-backend knowledge-flow-backend control-plane-backend frontend

.DEFAULT_GOAL := help

##@ Code quality

.PHONY: code-quality
code-quality: ## Run code quality checks in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Running code-quality in $$dir ************"; \
		$(MAKE) -C $$dir code-quality; \
	done

.PHONY: code-quality-fix
code-quality-fix: ## Auto-fix formatting/imports/linting in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Running code-quality fixes in $$dir ************"; \
		$(MAKE) -C $$dir lint-fix import-order-fix format-fix; \
	done

.PHONY: clean
clean: ## Clean all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Cleaning $$dir ************"; \
		$(MAKE) -C $$dir clean; \
	done

##@ Tests

.PHONY: test
test: ## Run non-integration test suites in backend submodules
	@set -e; \
	for dir in $(TEST_DIRS); do \
		echo "************ Running tests in $$dir ************"; \
		env -u VIRTUAL_ENV $(MAKE) -C $$dir test; \
	done

##@ Run

.PHONY: run-frontend
run-frontend: ## Run frontend only
	$(MAKE) -C frontend run

.PHONY: run-agentic
run-agentic: ## Run agentic backend API only
	$(MAKE) -C agentic-backend run

.PHONY: run-knowledge-flow
run-knowledge-flow: ## Run knowledge-flow backend API only
	$(MAKE) -C knowledge-flow-backend run

.PHONY: run-control-plane
run-control-plane: ## Run control-plane backend API only
	$(MAKE) -C control-plane-backend run

.PHONY: dev
dev:  ## Start development environment in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Starting dev environment in $$dir ************"; \
		$(MAKE) -C $$dir dev & \
	done; \
	wait

##@ Docker

.PHONY: docker-build
docker-build: ## Build Docker images for agentic, knowledge-flow, control-plane, and frontend
	@set -e; \
	for dir in $(DOCKER_BUILD_DIRS); do \
		echo "************ Building Docker image in $$dir ************"; \
		$(MAKE) -C $$dir docker-build; \
	done

##@ Configuration

MISTRAL_API_KEY ?=

.PHONY: use-mistral
use-mistral: ## Switch all config files to use Mistral as LLM provider (usage: make use-mistral [MISTRAL_API_KEY=<key>])
	@echo "--- agentic-backend: models_catalog.yaml ---"
	yq -i '.default_profile_by_capability.chat = "default.chat.mistral"' agentic-backend/config/models_catalog.yaml
	yq -i '.default_profile_by_capability.language = "default.language.mistral"' agentic-backend/config/models_catalog.yaml
	yq -i 'del(.profiles[] | select(.profile_id == "default.chat.mistral" or .profile_id == "default.language.mistral"))' agentic-backend/config/models_catalog.yaml
	yq -i '.profiles = [{"profile_id": "default.chat.mistral", "capability": "chat", "model": {"provider": "openai", "name": "mistral-medium-latest", "settings": {"base_url": "https://api.mistral.ai/v1"}}}, {"profile_id": "default.language.mistral", "capability": "language", "model": {"provider": "openai", "name": "mistral-medium-latest", "settings": {"base_url": "https://api.mistral.ai/v1"}}}] + .profiles' agentic-backend/config/models_catalog.yaml
	@echo "--- knowledge-flow-backend: configuration_prod.yaml ---"
	yq -i '.chat_model.name = "mistral-medium-latest" | .chat_model.settings = {"base_url": "https://api.mistral.ai/v1"}' knowledge-flow-backend/config/configuration_prod.yaml
	yq -i '.embedding_model.name = "mistral-embed" | .embedding_model.settings = {"base_url": "https://api.mistral.ai/v1", "check_embedding_ctx_length": false}' knowledge-flow-backend/config/configuration_prod.yaml
	yq -i '.vision_model.name = "mistral-medium-latest" | .vision_model.settings = {"base_url": "https://api.mistral.ai/v1"}' knowledge-flow-backend/config/configuration_prod.yaml
	yq -i '.storage.vector_store.index = "vector-index-mistral"' knowledge-flow-backend/config/configuration_prod.yaml
	@echo "--- knowledge-flow-backend: configuration_worker.yaml ---"
	yq -i '.chat_model.name = "mistral-medium-latest" | .chat_model.settings = {"base_url": "https://api.mistral.ai/v1"}' knowledge-flow-backend/config/configuration_worker.yaml
	yq -i '.embedding_model.name = "mistral-embed" | .embedding_model.settings = {"base_url": "https://api.mistral.ai/v1", "check_embedding_ctx_length": false}' knowledge-flow-backend/config/configuration_worker.yaml
	yq -i '.vision_model.name = "mistral-medium-latest" | .vision_model.settings = {"base_url": "https://api.mistral.ai/v1"}' knowledge-flow-backend/config/configuration_worker.yaml
	yq -i '.storage.vector_store.index = "vector-index-mistral"' knowledge-flow-backend/config/configuration_worker.yaml
	@echo "--- deploy/local/k3d: values-local.yaml ---"
	yq -i '.applications."agentic-backend".models_catalog.default_profile_by_capability.chat = "default.chat.mistral"' deploy/local/k3d/values-local.yaml
	yq -i '.applications."agentic-backend".models_catalog.default_profile_by_capability.language = "default.language.mistral"' deploy/local/k3d/values-local.yaml
	yq -i 'del(.applications."agentic-backend".models_catalog.profiles[] | select(.profile_id == "default.chat.mistral" or .profile_id == "default.language.mistral"))' deploy/local/k3d/values-local.yaml
	yq -i '.applications."agentic-backend".models_catalog.profiles = [{"profile_id": "default.chat.mistral", "capability": "chat", "model": {"provider": "openai", "name": "mistral-medium-latest", "settings": {"base_url": "https://api.mistral.ai/v1"}}}, {"profile_id": "default.language.mistral", "capability": "language", "model": {"provider": "openai", "name": "mistral-medium-latest", "settings": {"base_url": "https://api.mistral.ai/v1"}}}] + .applications."agentic-backend".models_catalog.profiles' deploy/local/k3d/values-local.yaml
	yq -i '."x-kf-chat-model".provider = "openai" | ."x-kf-chat-model".name = "mistral-medium-latest" | ."x-kf-chat-model".settings = {"base_url": "https://api.mistral.ai/v1"}' deploy/local/k3d/values-local.yaml
	yq -i '."x-kf-embedding-model".provider = "openai" | ."x-kf-embedding-model".name = "mistral-embed" | ."x-kf-embedding-model".settings = {"base_url": "https://api.mistral.ai/v1", "check_embedding_ctx_length": false}' deploy/local/k3d/values-local.yaml
	yq -i '."x-kf-vision-model".provider = "openai" | ."x-kf-vision-model".name = "mistral-medium-latest" | ."x-kf-vision-model".settings = {"base_url": "https://api.mistral.ai/v1"}' deploy/local/k3d/values-local.yaml
	yq -i '."x-kf-storage".vector_store.index = "vector-index-mistral"' deploy/local/k3d/values-local.yaml
	@if [ -n "$(MISTRAL_API_KEY)" ]; then \
		echo "--- .env files: setting OPENAI_API_KEY to Mistral API key ---"; \
		for env_file in agentic-backend/config/.env knowledge-flow-backend/config/.env control-plane-backend/config/.env; do \
			if [ -f "$$env_file" ]; then \
				if grep -q '^OPENAI_API_KEY=' "$$env_file"; then \
					sed -i 's|^OPENAI_API_KEY=.*|OPENAI_API_KEY="$(MISTRAL_API_KEY)"|' "$$env_file"; \
				else \
					echo 'OPENAI_API_KEY="$(MISTRAL_API_KEY)"' >> "$$env_file"; \
				fi; \
				echo "  Updated $$env_file"; \
			fi; \
		done; \
	fi
	@echo ""
	@echo "Done. Reminder: Mistral uses OPENAI_API_KEY as its API key (OpenAI-compatible provider)."
	@if [ -z "$(MISTRAL_API_KEY)" ]; then \
		echo "  OPENAI_API_KEY was NOT updated. Pass MISTRAL_API_KEY=<key> to also set it in .env files."; \
	fi

##@ Tools

.PHONY: install-wtf
install-wtf: ## Install the wtf worktree CLI locally (uv tool install, or fallback to pip)
	@if command -v uv >/dev/null 2>&1; then \
		uv tool install --editable scripts/wtf; \
	else \
		pip install --editable scripts/wtf; \
	fi

##@ Release

VERSION ?=

.PHONY: set-version
set-version: ## Update project version everywhere (usage: make set-version VERSION=x.y.z)
	@if [ -z "$(VERSION)" ]; then echo "ERROR: VERSION is required. Usage: make set-version VERSION=x.y.z"; exit 1; fi
	$(eval PY_VERSION := $(shell echo "$(VERSION)" | sed 's/-/+/'))
	@echo "Setting version to $(VERSION) (Python: $(PY_VERSION))..."
	@echo "--- Helm chart ---"
	sed -i 's/^version: .*/version: $(VERSION)/' deploy/charts/fred/Chart.yaml
	sed -i 's/^appVersion: .*/appVersion: $(VERSION)/' deploy/charts/fred/Chart.yaml
	@echo "--- fred-core ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' fred-core/pyproject.toml
	cd fred-core && uv lock
	@echo "--- agentic-backend ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' agentic-backend/pyproject.toml
	cd agentic-backend && uv lock
	@echo "--- knowledge-flow-backend ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' knowledge-flow-backend/pyproject.toml
	cd knowledge-flow-backend && uv lock
	@echo "--- frontend ---"
	cd frontend && npm version $(VERSION) --no-git-tag-version
	@echo "Version updated to $(VERSION) in all components."

include scripts/makefiles/help.mk

# =============================================================================
# k3d local deployment
# =============================================================================

K3D_CLUSTER    ?= fred
K3D_NAMESPACE  ?= fred
HELM_RELEASE   ?= fred-app
HELM_CHART     ?= deploy/charts/fred
HELM_VALUES    ?= deploy/local/k3d/values-local.yaml

# Image names (must match values-local.yaml)
AGENTIC_IMAGE  ?= ghcr.io/thalesgroup/fred-agent/agentic-backend:0.1
KF_IMAGE       ?= ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:0.1
FRONTEND_IMAGE ?= ghcr.io/thalesgroup/fred-agent/frontend:0.1
CP_IMAGE       ?= ghcr.io/thalesgroup/fred-agent/control-plane-backend:0.1

##@ k3d Deployment

.PHONY: k3d-build
k3d-build: ## Build Docker images for all services (in parallel)
	@echo "🔨 Building all images in parallel..."
	@$(MAKE) -j4 build-agentic build-kf build-frontend build-cp

.PHONY: build-agentic
build-agentic:
	$(MAKE) -C agentic-backend docker-build

.PHONY: build-kf
build-kf:
	$(MAKE) -C knowledge-flow-backend docker-build

.PHONY: build-frontend
build-frontend:
	$(MAKE) -C frontend docker-build

.PHONY: build-cp
build-cp:
	$(MAKE) -C control-plane-backend docker-build

.PHONY: k3d-import
k3d-import: ## Import Docker images into k3d cluster
	@echo "📦 Importing images into k3d cluster '$(K3D_CLUSTER)'..."
	k3d image import $(AGENTIC_IMAGE) $(KF_IMAGE) $(FRONTEND_IMAGE) $(CP_IMAGE) -c $(K3D_CLUSTER)

.PHONY: k3d-deploy
k3d-deploy: k3d-build k3d-import k3d-deploy-only ## Build, import, and deploy all services to k3d

.PHONY: k3d-deploy-only
k3d-deploy-only: ## Deploy/upgrade Helm chart (images must already be in k3d)
	@echo "🚀 Deploying $(HELM_RELEASE) to namespace $(K3D_NAMESPACE)..."
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		--namespace $(K3D_NAMESPACE) \
		--create-namespace \
		-f $(HELM_VALUES)
	@echo "🔄 Forcing pods to restart to pick up newest local images..."
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) agentic-backend knowledge-flow-backend frontend control-plane-backend

# --- Selective Turbo Deploy Targets ---

.PHONY: k3d-turbo-backend
k3d-turbo-backend: build-agentic ## Turbo: build, import and roll agentic-backend ONLY
	k3d image import $(AGENTIC_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) agentic-backend

.PHONY: k3d-turbo-kf
k3d-turbo-kf: build-kf ## Turbo: build, import and roll knowledge-flow-backend ONLY
	k3d image import $(KF_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) knowledge-flow-backend

.PHONY: k3d-turbo-frontend
k3d-turbo-frontend: build-frontend ## Turbo: build, import and roll frontend ONLY
	k3d image import $(FRONTEND_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) frontend

.PHONY: k3d-turbo-cp
k3d-turbo-cp: build-cp ## Turbo: build, import and roll control-plane-backend ONLY
	k3d image import $(CP_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) control-plane-backend

.PHONY: k3d-turbo-all
k3d-turbo-all: k3d-build ## Turbo: build and import all images, then roll all deployments
	k3d image import $(AGENTIC_IMAGE) $(KF_IMAGE) $(FRONTEND_IMAGE) $(CP_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) agentic-backend knowledge-flow-backend frontend control-plane-backend

.PHONY: k3d-undeploy
k3d-undeploy: ## Uninstall the Helm release
	@echo "🗑️  Uninstalling $(HELM_RELEASE)..."
	helm uninstall $(HELM_RELEASE) --namespace $(K3D_NAMESPACE)

.PHONY: k3d-status
k3d-status: ## Show status of pods in the fred namespace
	@echo "📊 Pod status in namespace $(K3D_NAMESPACE):"
	kubectl get pods -n $(K3D_NAMESPACE) -o wide
	@echo ""
	@echo "📊 Services:"
	kubectl get svc -n $(K3D_NAMESPACE)

.PHONY: k3d-logs-agentic
k3d-logs-agentic: ## Tail logs for agentic-backend
	kubectl logs -n $(K3D_NAMESPACE) -l app=agentic-backend -f --tail=100

.PHONY: k3d-logs-kf
k3d-logs-kf: ## Tail logs for knowledge-flow-backend
	kubectl logs -n $(K3D_NAMESPACE) -l app=knowledge-flow-backend -f --tail=100

.PHONY: k3d-logs-frontend
k3d-logs-frontend: ## Tail logs for frontend
	kubectl logs -n $(K3D_NAMESPACE) -l app=frontend -f --tail=100
