CODE_QUALITY_DIRS := libs/fred-core libs/fred-sdk libs/fred-runtime libs/fred-capability-writable-document libs/fred-capability-ppt-filler apps/fred-agents apps/control-plane-backend apps/knowledge-flow-backend apps/frontend
TEST_DIRS := libs/fred-core libs/fred-sdk libs/fred-runtime libs/fred-capability-writable-document libs/fred-capability-ppt-filler apps/fred-agents apps/control-plane-backend apps/knowledge-flow-backend apps/frontend
DOCKER_BUILD_DIRS := apps/fred-agents apps/knowledge-flow-backend apps/control-plane-backend apps/frontend
RUN_DIRS := apps/control-plane-backend apps/fred-agents apps/knowledge-flow-backend apps/frontend
ENV_APPS := apps/control-plane-backend apps/fred-agents apps/knowledge-flow-backend

.DEFAULT_GOAL := help

##@ Code quality

.PHONY: update-uv-locks
update-uv-locks: ## Update uv lock state in subprojects except frontend
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		case "$$dir" in \
			*frontend*) continue ;; \
		esac; \
		echo "************ Refreshing uv lock state in $$dir ************"; \
		env -u VIRTUAL_ENV $(MAKE) -C $$dir update; \
	done

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
		$(MAKE) -C $$dir code-quality-fix; \
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
test: ## Run non-integration test suites in all submodules and print coverage summary
	@set -e; \
	for dir in $(TEST_DIRS); do \
		echo "************ Running tests in $$dir ************"; \
		env -u VIRTUAL_ENV $(MAKE) -C $$dir test; \
	done
	@echo ""
	@echo "  ── Coverage summary ───────────────────────────────────────────"
	@for dir in $(TEST_DIRS); do \
		if [ -f "$$dir/.venv/bin/coverage" ] && [ -f "$$dir/.coverage" ]; then \
			pct=$$(cd "$$dir" && .venv/bin/coverage report --skip-empty 2>/dev/null | awk '/^TOTAL/{print $$NF}'); \
			printf "  %-44s %s\n" "$$dir" "$${pct:-n/a}"; \
		elif [ -f "$$dir/coverage/coverage-summary.json" ]; then \
			pct=$$(node -e "const r=require('./$$dir/coverage/coverage-summary.json');const t=r.total;const lines=t.lines;process.stdout.write(Math.round(lines.pct)+'%')" 2>/dev/null); \
			printf "  %-44s %s\n" "$$dir" "$${pct:-n/a}"; \
		else \
			printf "  %-44s %s\n" "$$dir" "no data"; \
		fi; \
	done
	@echo "  ───────────────────────────────────────────────────────────────"

##@ Validation

.PHONY: validation-report
validation-report: ## Run the live cross-app validation suite (requires infra + running apps - see validation/README.md)
	$(MAKE) -C validation validation-report

##@ Setup

.PHONY: setup-env
setup-env: ## Create each backend's .env from its .env.template (idempotent), fill in local-dev secrets that docker-compose already fixes to the same value everywhere, prompt once for a model provider API key
	@set -e; \
	for dir in $(ENV_APPS); do \
		if [ ! -f "$$dir/config/.env" ]; then \
			cp "$$dir/config/.env.template" "$$dir/config/.env"; \
			echo "************ Created $$dir/config/.env from template ************"; \
		else \
			echo "************ $$dir/config/.env already exists, leaving it untouched ************"; \
		fi; \
	done
	@# fred-deployment-factory's docker-compose fixes these to the same value everywhere
	@# (Postgres/OpenSearch/OpenFGA/MinIO passwords, every Keycloak client secret) -- only
	@# ever fills a placeholder that's still literally empty, never overwrites a real value.
	@for dir in $(ENV_APPS); do \
		f="$$dir/config/.env"; \
		[ -f "$$f" ] || continue; \
		for key in FRED_POSTGRES_PASSWORD OPENSEARCH_PASSWORD OPENFGA_API_TOKEN MINIO_SECRET_KEY KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET KEYCLOAK_AGENTIC_CLIENT_SECRET KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET; do \
			if grep -q "^$$key=\"\"" "$$f" 2>/dev/null; then \
				sed -i "s/^$$key=\"\"/$$key=\"Azerty123_\"/" "$$f"; \
			fi; \
		done; \
	done
	@# knowledge-flow-backend's own .env.template still defaults CONFIG_FILE to configuration.yaml
	@# (doc drift vs. the other two apps) -- only fix it if it's still exactly that stale
	@# template default, never touch a value a developer deliberately set to something else.
	@if [ -f apps/knowledge-flow-backend/config/.env ] && grep -qE '^CONFIG_FILE="?\./config/configuration\.yaml"?$$' apps/knowledge-flow-backend/config/.env; then \
		sed -i 's|^CONFIG_FILE=.*|CONFIG_FILE="./config/configuration_prod.yaml"|' apps/knowledge-flow-backend/config/.env; \
		echo "************ Fixed knowledge-flow-backend CONFIG_FILE to configuration_prod.yaml ************"; \
	fi
	@# Prompt once (not per app) for a model provider key, only if neither fred-agents app
	@# already has one -- skipped entirely in a non-interactive shell (no stdin to read).
	@if [ -t 0 ] && ! grep -qE '^(OPENAI_API_KEY|ANTHROPIC_API_KEY)="[^"]+"' apps/fred-agents/config/.env 2>/dev/null; then \
		read -p "Enter an OpenAI API key for local dev (blank to skip, add it later yourself): " api_key; \
		if [ -n "$$api_key" ]; then \
			sed -i "s/^OPENAI_API_KEY=\"\"/OPENAI_API_KEY=\"$$api_key\"/" apps/fred-agents/config/.env; \
			[ -f apps/knowledge-flow-backend/config/.env ] && sed -i "s/^OPENAI_API_KEY=\"\"/OPENAI_API_KEY=\"$$api_key\"/" apps/knowledge-flow-backend/config/.env; \
		fi; \
	fi
	@echo "✓ setup-env done. Review apps/*/config/.env yourself for anything beyond local docker-compose defaults (Azure, proxy, Prometheus, ...)."

##@ Run

.PHONY: run-frontend
run-frontend: ## Run frontend only
	$(MAKE) -C apps/frontend run

.PHONY: run-fred-agents
run-fred-agents: ## Run fred-agents API only
	$(MAKE) -C apps/fred-agents run

.PHONY: run-knowledge-flow
run-knowledge-flow: ## Run knowledge-flow backend API only
	$(MAKE) -C apps/knowledge-flow-backend run

.PHONY: run-control-plane
run-control-plane: ## Run control-plane backend API only
	$(MAKE) -C apps/control-plane-backend run

.PHONY: run
run: ## Start control-plane, fred-agents, knowledge-flow, and frontend together in one terminal (Ctrl+C stops all four)
	@set -e; \
	for dir in $(RUN_DIRS); do \
		echo "************ Starting $$dir ************"; \
		$(MAKE) -C $$dir run & \
	done; \
	wait

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
docker-build: ## Build Docker images for fred-agents, knowledge-flow, control-plane, and frontend
	@set -e; \
	for dir in $(DOCKER_BUILD_DIRS); do \
		echo "************ Building Docker image in $$dir ************"; \
		$(MAKE) -C $$dir docker-build; \
	done

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
	@echo "--- libs/fred-core ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' libs/fred-core/pyproject.toml
	cd libs/fred-core && uv lock
	@echo "--- fred-agents ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' apps/fred-agents/pyproject.toml
	cd apps/fred-agents && uv lock
	@echo "--- knowledge-flow-backend ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' apps/knowledge-flow-backend/pyproject.toml
	cd apps/knowledge-flow-backend && uv lock
	@echo "--- control-plane-backend ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' apps/control-plane-backend/pyproject.toml
	cd apps/control-plane-backend && uv lock
	@echo "--- frontend ---"
	cd apps/frontend && npm version $(VERSION) --no-git-tag-version
	@echo "Version updated to $(VERSION) in all components."

##@ Migration Schema Snapshots

SNAPSHOTS_DIR ?= $(CURDIR)/target/migration-snapshots

.PHONY: db-snapshots
db-snapshots: ## Dump schema after each migration for migratable backends into target/migration-snapshots/
	@set -e; \
	for dir in apps/control-plane-backend apps/knowledge-flow-backend; do \
		echo "************ Snapshotting $$dir ************"; \
		$(MAKE) -C $$dir db-snapshots DB_SNAPSHOTS_DIR=$(SNAPSHOTS_DIR); \
	done

##@ Database Migrations (combined)

MIGRATION_COMPOSE    := scripts/docker-compose.postgres.yml
PG_COMBINED_URL      := postgresql+asyncpg://test:test@localhost:5433/test_migrations
SQLITE_COMBINED_DB   := /tmp/fred_combined_migrations.db
# One entry per Alembic tree. These lists are hardcoded, not discovery: a new
# tree is exercised by nothing until it is added to all three targets below.
CP_DIR               := apps/control-plane-backend
KF_DIR               := apps/knowledge-flow-backend
RT_DIR               := libs/fred-runtime
WD_DIR               := libs/fred-capability-writable-document
CP_UV                := $(CP_DIR)/.venv/bin/uv
KF_UV                := $(KF_DIR)/.venv/bin/uv
RT_UV                := $(RT_DIR)/.venv/bin/uv
WD_UV                := $(WD_DIR)/.venv/bin/uv

.PHONY: db-check-combined-heads
db-check-combined-heads: ## assert each Alembic tree has exactly one head (no branch conflicts)
	$(MAKE) -C $(CP_DIR) db-check-heads
	$(MAKE) -C $(KF_DIR) db-check-heads
	$(MAKE) -C $(RT_DIR) db-check-heads
	$(MAKE) -C $(WD_DIR) db-check-heads

.PHONY: db-check-combined-postgres-up
db-check-combined-postgres-up: ## start the PostgreSQL container for combined migration checks
	docker compose -f $(MIGRATION_COMPOSE) up -d --wait

.PHONY: db-check-combined-postgres-down
db-check-combined-postgres-down: ## stop and wipe the PostgreSQL container for combined migration checks
	docker compose -f $(MIGRATION_COMPOSE) down -v

.PHONY: db-check-combined-sqlite
db-check-combined-sqlite: ## upgrade every Alembic tree against the same SQLite DB, check for drift, then downgrade
	@echo "=== Combined SQLite migration check: upgrade ==="
	@rm -f $(SQLITE_COMBINED_DB)
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(CP_UV) run --directory $(CP_DIR) alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(KF_UV) run --directory $(KF_DIR) alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory $(RT_DIR) alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(WD_UV) run --directory $(WD_DIR) alembic upgrade head
	@echo "=== Combined SQLite migration check: drift check ==="
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(CP_UV) run --directory $(CP_DIR) alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(KF_UV) run --directory $(KF_DIR) alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory $(RT_DIR) alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(WD_UV) run --directory $(WD_DIR) alembic check
	@echo "=== Combined SQLite migration check: downgrade ==="
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(WD_UV) run --directory $(WD_DIR) alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(KF_UV) run --directory $(KF_DIR) alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(CP_UV) run --directory $(CP_DIR) alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory $(RT_DIR) alembic downgrade base
	@rm -f $(SQLITE_COMBINED_DB)
	@echo "=== Combined SQLite migration check passed ==="

.PHONY: db-check-combined-postgres
db-check-combined-postgres: db-check-combined-postgres-down db-check-combined-postgres-up ## upgrade every Alembic tree against the same DB, check for drift, then downgrade
	@echo "=== Combined migration check: upgrade ==="
	DATABASE_URL="$(PG_COMBINED_URL)" $(CP_UV) run --directory $(CP_DIR) alembic upgrade head
	DATABASE_URL="$(PG_COMBINED_URL)" $(KF_UV) run --directory $(KF_DIR) alembic upgrade head
	DATABASE_URL="$(PG_COMBINED_URL)" $(RT_UV) run --directory $(RT_DIR) alembic upgrade head
	DATABASE_URL="$(PG_COMBINED_URL)" $(WD_UV) run --directory $(WD_DIR) alembic upgrade head
	@echo "=== Combined migration check: drift check ==="
	DATABASE_URL="$(PG_COMBINED_URL)" $(CP_UV) run --directory $(CP_DIR) alembic check
	DATABASE_URL="$(PG_COMBINED_URL)" $(KF_UV) run --directory $(KF_DIR) alembic check
	DATABASE_URL="$(PG_COMBINED_URL)" $(RT_UV) run --directory $(RT_DIR) alembic check
	DATABASE_URL="$(PG_COMBINED_URL)" $(WD_UV) run --directory $(WD_DIR) alembic check
	@echo "=== Combined migration check: downgrade ==="
	DATABASE_URL="$(PG_COMBINED_URL)" $(WD_UV) run --directory $(WD_DIR) alembic downgrade base
	DATABASE_URL="$(PG_COMBINED_URL)" $(KF_UV) run --directory $(KF_DIR) alembic downgrade base
	DATABASE_URL="$(PG_COMBINED_URL)" $(CP_UV) run --directory $(CP_DIR) alembic downgrade base
	DATABASE_URL="$(PG_COMBINED_URL)" $(RT_UV) run --directory $(RT_DIR) alembic downgrade base
	@echo "=== Combined migration check passed ==="
	$(MAKE) db-check-combined-postgres-down

include scripts/makefiles/help.mk
include scripts/makefiles/chart-schema.mk

# =============================================================================
# k3d local deployment
# =============================================================================

K3D_CLUSTER    ?= fred
K3D_NAMESPACE  ?= fred
HELM_RELEASE   ?= fred-app
HELM_CHART     ?= deploy/charts/fred
HELM_VALUES    ?= deploy/local/k3d/values-local.yaml
HELM_VALUES_BENCH ?= deploy/local/k3d/values-bench.yaml

# Image names
FRED_AGENTS_IMAGE ?= ghcr.io/thalesgroup/fred-agent/fred-agents:0.2
KF_IMAGE       ?= ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:0.2
FRONTEND_IMAGE ?= ghcr.io/thalesgroup/fred-agent/frontend:0.2
CP_IMAGE       ?= ghcr.io/thalesgroup/fred-agent/control-plane-backend:0.2

##@ k3d Deployment

.PHONY: k3d-build
k3d-build: ## Build Docker images for all services (in parallel)
	@echo "🔨 Building all images in parallel..."
	@$(MAKE) -j4 build-fred-agents build-kf build-frontend build-cp

.PHONY: build-fred-agents
build-fred-agents:
	$(MAKE) -C apps/fred-agents docker-build

.PHONY: build-kf
build-kf:
	$(MAKE) -C apps/knowledge-flow-backend docker-build

.PHONY: build-frontend
build-frontend:
	$(MAKE) -C apps/frontend docker-build

.PHONY: build-cp
build-cp:
	$(MAKE) -C apps/control-plane-backend docker-build

.PHONY: k3d-import
k3d-import: ## Import Docker images into k3d cluster
	@echo "📦 Importing images into k3d cluster '$(K3D_CLUSTER)'..."
	k3d image import $(FRED_AGENTS_IMAGE) $(KF_IMAGE) $(FRONTEND_IMAGE) $(CP_IMAGE) -c $(K3D_CLUSTER)

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
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) fred-agents knowledge-flow-backend frontend control-plane-backend

.PHONY: k3d-deploy-only-bench
k3d-deploy-only-bench: ## Deploy/upgrade Helm chart with local + bench values (images must already be in k3d)
	@echo "🚀 Deploying $(HELM_RELEASE) bench to namespace $(K3D_NAMESPACE)..."
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		--namespace $(K3D_NAMESPACE) \
		--create-namespace \
		-f $(HELM_VALUES) \
		-f $(HELM_VALUES_BENCH)
	@echo "🔄 Forcing pods to restart to pick up newest local images..."
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) fred-agents knowledge-flow-backend frontend control-plane-backend

# --- Selective Turbo Deploy Targets ---

.PHONY: k3d-turbo-fred-agents
k3d-turbo-fred-agents: build-fred-agents ## Turbo: build, import and roll fred-agents ONLY
	k3d image import $(FRED_AGENTS_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) fred-agents

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
	k3d image import $(FRED_AGENTS_IMAGE) $(KF_IMAGE) $(FRONTEND_IMAGE) $(CP_IMAGE) -c $(K3D_CLUSTER)
	kubectl rollout restart deployment -n $(K3D_NAMESPACE) fred-agents knowledge-flow-backend frontend control-plane-backend

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

.PHONY: k3d-logs-fred-agents
k3d-logs-fred-agents: ## Tail logs for fred-agents
	kubectl logs -n $(K3D_NAMESPACE) -l app=fred-agents -f --tail=100

.PHONY: k3d-logs-kf
k3d-logs-kf: ## Tail logs for knowledge-flow-backend
	kubectl logs -n $(K3D_NAMESPACE) -l app=knowledge-flow-backend -f --tail=100

.PHONY: k3d-logs-frontend
k3d-logs-frontend: ## Tail logs for frontend
	kubectl logs -n $(K3D_NAMESPACE) -l app=frontend -f --tail=100
