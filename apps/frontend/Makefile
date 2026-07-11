include ../../scripts/makefiles/config/INFO-frontend.mk

# ---------------------------------------------------------------------------
# Frontend Makefile
#
# Run `make` (or `make help`) to list every target grouped by purpose.
# Day-to-day work needs only a handful of targets — see the "Common workflows"
# block at the top of the help output. Everything else builds container images,
# publishes artifacts, or regenerates the backend API client.
#
# Internal plumbing targets (Node version check, dependency install) run
# automatically as prerequisites of the targets you call, so they are hidden
# from `make` help on purpose. Never invoke them directly.
# ---------------------------------------------------------------------------

.DEFAULT_GOAL := help

NODE_VERSION=22.13.0

##@ Common workflows
##> The commands you actually use day to day:
##>   make run             start the local dev server on http://localhost:5173
##>   make code-quality    type-check + prettier check — run this before committing
##>   make test            run the unit test suite with coverage
##>   make update-all-apis regenerate the API client after any backend change
##> First run installs npm dependencies automatically; later runs reuse them.

##@ Build

# check-node and node_modules are INTERNAL prerequisites. They carry no `##`
# description, so they do not appear in `make` help. They run automatically
# before any target that needs Node or installed dependencies — do not run
# them by hand.
.PHONY: check-node
check-node:
	@REQUIRED=$(NODE_VERSION); \
	CURRENT=$$(node -v | sed 's/^v//'); \
	verlte() { [ "$$1" = "$$2" ] && return 0 || [  "$$(printf '%s\n' "$$1" "$$2" | sort -V | head -n1)" = "$$1" ]; }; \
	if ! verlte "$$REQUIRED" "$$CURRENT"; then \
		echo "Node.js v$$REQUIRED or higher is required, but found v$$CURRENT. Please use the correct version."; \
		exit 1; \
	fi


# node_modules: install dependencies (reproducibly via `npm ci` when a lockfile
# exists, otherwise `npm install`). Runs only when package.json is newer than
# the installed tree, so repeated builds are fast.
.PHONY: node_modules
node_modules: check-node package.json
	@if [ -f package-lock.json ]; then \
		npm ci --no-audit --no-fund --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000; \
	else \
		npm install --no-audit --no-fund --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000; \
	fi

.PHONY: regen-lockfile
regen-lockfile: check-node ## Regenerate package-lock.json from scratch inside a clean Node container
	docker run --rm -it -v $(CURDIR):/src -w /src node:22.13.0 bash -c "rm -rf node_modules package-lock.json && npm install"

.PHONY: build
build: check-node node_modules ## Production build (Vite/Rollup) into dist/ — the artifact shipped in the image
	npm run build

.PHONY: helm-package
helm-package: ## Package the frontend Helm chart into a .tgz archive
	helm package helm-chart/

##@ Docker

.PHONY: docker-build
docker-build: ## Build the production frontend Docker image (nginx serving the built dist/)
	docker build \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-push
docker-push: ## Push the built frontend Docker image to the registry
	docker push $(IMAGE_FULL)

.PHONY: run-docker
run-docker: ## Run the built image in a container, proxying backend calls to services on the host
	@echo "🚀 Running frontend in Docker..."
	docker run --rm -it \
		--name $(FRONTEND_CONTAINER_NAME) \
		--network $(FRONTEND_DOCKER_NETWORK) \
		--add-host=host.docker.internal:host-gateway \
		-e FRONTEND_AGENTIC_UPSTREAM=$(FRONTEND_AGENTIC_UPSTREAM) \
		-e FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=$(FRONTEND_KNOWLEDGE_FLOW_UPSTREAM) \
		-e FRONTEND_CONTROL_PLANE_UPSTREAM=$(FRONTEND_CONTROL_PLANE_UPSTREAM) \
		-p $(FRONTEND_HOST_PORT):$(FRONTEND_CONTAINER_PORT) \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Alias for run-docker (kept for backward compatibility)

##@ Run

.PHONY: run
run: check-node node_modules ## Start the local Vite dev server on :5173 (HMR; proxies backend calls) — the everyday command
	VITE_DEV_USERNAME=$(shell whoami) npm run dev

##@ Code quality

.PHONY: type-check
type-check: node_modules ## Type-check with tsc (no files emitted)
	npx tsc --noEmit

.PHONY: format-check
format-check: node_modules ## Check formatting with prettier (fails on unformatted files, writes nothing)
	npx prettier . --check

.PHONY: format-fix
format-fix: node_modules ## Reformat the codebase in place with prettier
	npx prettier . --write

# knip (unused-export/dependency detection) is not wired in yet; see the
# code-quality TODO below. Uncomment once the config is stable.
# .PHONY: knip
# knip: node_modules ## Find unused exports, files and dependencies
# 	npx knip

# .PHONY: knip-fix
# knip-fix: node_modules ## Auto-fix unused exports and files reported by knip
# 	npx knip --fix --format

# TODO: add `knip` to the prerequisites below once it is wired in.
.PHONY: code-quality
code-quality: type-check format-check  ## Run all checks (type-check + prettier) — the gate to pass before committing
	@echo "All frontend code quality checks completed"

# TODO: add `knip-fix` to the prerequisites below once knip is wired in.
.PHONY: code-quality-fix
code-quality-fix: format-fix  ## Auto-fix what code-quality flags (currently prettier formatting)
	@echo "Frontend auto-fix tasks completed"

##@ Tests

.PHONY: test
test: check-node node_modules ## Run the unit test suite (vitest) with coverage
	npm run test:coverage

##@ API client generation

# The frontend RTK Query client and TypeScript types are GENERATED from each
# backend's OpenAPI spec — never hand-edit them. Re-run the matching target
# after changing a backend controller or model, and commit the regenerated
# *OpenApi.ts alongside the backend change.
.PHONY: update-all-apis
update-all-apis: update-knowledge-flow-api update-control-plane-api update-runtime-api update-evaluation-api ## Regenerate the API client for ALL backends at once
	@echo "All backend API clients regenerated"

.PHONY: update-knowledge-flow-api
update-knowledge-flow-api: check-node node_modules ## Regenerate the API client for the knowledge-flow backend only
	@echo "🔧 Generating knowledge-flow backend OpenAPI specification..."
	cd ../../apps/knowledge-flow-backend && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for knowledge-flow backend..."
	npx --no-install @rtk-query/codegen-openapi src/slices/knowledgeFlow/knowledgeFlowOpenApiConfig.json

.PHONY: update-control-plane-api
update-control-plane-api: check-node node_modules ## Regenerate the API client for the control-plane backend only
	@echo "🔧 Generating control-plane backend OpenAPI specification..."
	cd ../control-plane-backend && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for control-plane backend..."
	npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json

.PHONY: update-runtime-api
update-runtime-api: check-node node_modules ## Regenerate the API client for fred-runtime only
	@echo "🔧 Generating fred-runtime OpenAPI specification..."
	cd ../../libs/fred-runtime && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for fred-runtime..."
	npx --no-install @rtk-query/codegen-openapi src/slices/runtime/runtimeOpenApiConfig.json

.PHONY: update-evaluation-api
update-evaluation-api: check-node node_modules ## Regenerate the API client for the fred-evaluation backend only
	@echo "🔧 Generating fred-evaluation-backend OpenAPI specification..."
	cd ../fred-evaluation-backend && make generate-openapi
	@echo "🎯 Generating RTK Query hooks for fred-evaluation-backend..."
	npx --no-install @rtk-query/codegen-openapi src/slices/evaluation/evaluationOpenApiConfig.json

# Per-capability client (AGENT-CAPABILITY-RFC §9.1, #1979): each capability's
# router has its OWN OpenAPI document (dumped by the runtime CLI) and its OWN
# generated slice under features/capabilities/<id>/api/. Repo rule extends
# verbatim: touched a capability router → regenerate that capability's slice.
.PHONY: update-demo-echo-capability-api
update-demo-echo-capability-api: check-node node_modules ## Regenerate the demo_echo capability client only
	@echo "🔧 Dumping demo_echo capability OpenAPI document..."
	cd ../../libs/fred-runtime && $(MAKE) --no-print-directory dev >/dev/null && \
		.venv/bin/python -m fred_runtime dump-openapi demo_echo \
		> ../../apps/frontend/src/rework/features/capabilities/demo_echo/api/openapi.json
	@echo "🎯 Generating RTK Query hooks for demo_echo capability..."
	npx --no-install @rtk-query/codegen-openapi src/rework/features/capabilities/demo_echo/api/demoEchoCapabilityOpenApiConfig.json

##@ Clean

.PHONY: clean
clean: ## Remove build output (build/, dist/) and installed node_modules
	rm -rf $(CURDIR)/build
	rm -rf $(CURDIR)/dist
	rm -rf $(CURDIR)/node_modules
	rm -rf node_modules

.PHONY: clean-docker
clean-docker: ## Remove the frontend container and prune dangling Docker images
	docker rm -f $(FRONTEND_CONTAINER_NAME) || true
	docker image prune -f

.PHONY: full-clean
full-clean: clean clean-docker ## Full cleanup: local build output + Docker artifacts

##@ Image and Helm chart publishing

.PHONY: helm-push
helm-push: ## Push the packaged Helm chart to the GitLab chart registry
	curl --fail-with-body --request POST \
         --form "chart=@${HELM_ARCHIVE}" \
         --user ${GITLAB_USER}:${GITLAB_TOKEN} \
         https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts


include ../../scripts/makefiles/help.mk

# Docker runtime defaults
FRONTEND_CONTAINER_NAME ?= frontend
FRONTEND_DOCKER_NETWORK ?= bridge
FRONTEND_HOST_PORT ?= 5173
FRONTEND_CONTAINER_PORT ?= 8080
FRONTEND_AGENTIC_UPSTREAM ?= http://host.docker.internal:8000
FRONTEND_KNOWLEDGE_FLOW_UPSTREAM ?= http://host.docker.internal:8111
FRONTEND_CONTROL_PLANE_UPSTREAM ?= http://host.docker.internal:8222
