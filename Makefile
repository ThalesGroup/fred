CODE_QUALITY_DIRS := fred-core agentic-backend knowledge-flow-backend
TEST_DIRS := agentic-backend knowledge-flow-backend

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

.PHONY: dev
dev:  ## Start development environment in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Starting dev environment in $$dir ************"; \
		$(MAKE) -C $$dir dev & \
	done; \
	wait

##@ Release

VERSION ?=

.PHONY: set-version
set-version: ## Update project version everywhere (usage: make set-version VERSION=x.y.z)
	@if [ -z "$(VERSION)" ]; then echo "ERROR: VERSION is required. Usage: make set-version VERSION=x.y.z"; exit 1; fi
	@echo "Setting version to $(VERSION)..."
	@echo "--- Helm chart ---"
	sed -i 's/^version: .*/version: $(VERSION)/' deploy/charts/fred/Chart.yaml
	sed -i 's/^appVersion: .*/appVersion: $(VERSION)/' deploy/charts/fred/Chart.yaml
	@echo "--- fred-core ---"
	sed -i 's/^version = .*/version = "$(VERSION)"/' fred-core/pyproject.toml
	cd fred-core && uv lock
	@echo "--- agentic-backend ---"
	sed -i 's/^version = .*/version = "$(VERSION)"/' agentic-backend/pyproject.toml
	cd agentic-backend && uv lock
	@echo "--- knowledge-flow-backend ---"
	sed -i 's/^version = .*/version = "$(VERSION)"/' knowledge-flow-backend/pyproject.toml
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

##@ k3d Deployment

.PHONY: k3d-build
k3d-build: ## Build Docker images for all services
	@echo "🔨 Building agentic-backend..."
	$(MAKE) -C agentic-backend docker-build
	@echo "🔨 Building knowledge-flow-backend..."
	$(MAKE) -C knowledge-flow-backend docker-build
	@echo "🔨 Building frontend..."
	$(MAKE) -C frontend docker-build

.PHONY: k3d-import
k3d-import: ## Import Docker images into k3d cluster
	@echo "📦 Importing images into k3d cluster '$(K3D_CLUSTER)'..."
	k3d image import $(AGENTIC_IMAGE) -c $(K3D_CLUSTER)
	k3d image import $(KF_IMAGE) -c $(K3D_CLUSTER)
	k3d image import $(FRONTEND_IMAGE) -c $(K3D_CLUSTER)

.PHONY: k3d-deploy
k3d-deploy: k3d-build k3d-import k3d-deploy-only ## Build, import, and deploy all services to k3d

.PHONY: k3d-deploy-only
k3d-deploy-only: ## Deploy/upgrade Helm chart (images must already be in k3d)
	@echo "🚀 Deploying $(HELM_RELEASE) to namespace $(K3D_NAMESPACE)..."
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		--namespace $(K3D_NAMESPACE) \
		--create-namespace \
		-f $(HELM_VALUES) \
		--wait --timeout 5m

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
