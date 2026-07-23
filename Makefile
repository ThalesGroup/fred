CODE_QUALITY_DIRS := libs/fred-core libs/fred-sdk libs/fred-runtime libs/fred-capability-writable-document libs/fred-capability-ppt-filler apps/fred-agents apps/control-plane-backend apps/knowledge-flow-backend apps/frontend
TEST_DIRS := libs/fred-core libs/fred-sdk libs/fred-runtime libs/fred-capability-writable-document libs/fred-capability-ppt-filler apps/fred-agents apps/control-plane-backend apps/knowledge-flow-backend apps/frontend
DOCKER_BUILD_DIRS := apps/fred-agents apps/knowledge-flow-backend apps/control-plane-backend apps/frontend

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

EVAL_REPO := ../fred-agent-evaluator

.PHONY: install-evaluation
install-evaluation: ## Install fred-agent-evaluator deps (sibling repo)
	@[ -d $(EVAL_REPO) ] || { echo "Clone fred-agent-evaluator as a sibling of fred first"; exit 1; }
	$(MAKE) -C $(EVAL_REPO)/apps/fred-evaluation-backend dev-scoring

.PHONY: run-evaluation
run-evaluation: ## Run the evaluation API (sibling repo)
	$(MAKE) -C $(EVAL_REPO)/apps/fred-evaluation-backend run

.PHONY: run-evaluation-worker
run-evaluation-worker: ## Run the evaluation worker (sibling repo)
	$(MAKE) -C $(EVAL_REPO)/apps/fred-evaluation-backend run-worker

.PHONY: run-evaluation-prod
run-evaluation-prod: ## Run the evaluation API with prod-like configuration (sibling repo)
	$(MAKE) -C $(EVAL_REPO)/apps/fred-evaluation-backend rrun-prod

.PHONY: run-evaluation-worker-prod
run-evaluation-worker-prod: ## Run the evaluation worker with prod-like configuration, M2M enabled (sibling repo)
	$(MAKE) -C $(EVAL_REPO)/apps/fred-evaluation-backend run-worker-prod

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
CP_UV                := apps/control-plane-backend/.venv/bin/uv
KF_UV                := apps/knowledge-flow-backend/.venv/bin/uv
RT_UV                := libs/fred-runtime/.venv/bin/uv

.PHONY: db-check-combined-heads
db-check-combined-heads: ## assert each migratable backend has exactly one Alembic head (no branch conflicts)
	$(MAKE) -C apps/control-plane-backend db-check-heads
	$(MAKE) -C apps/knowledge-flow-backend db-check-heads
	$(MAKE) -C libs/fred-runtime db-check-heads

.PHONY: db-check-combined-postgres-up
db-check-combined-postgres-up: ## start the PostgreSQL container for combined migration checks
	docker compose -f $(MIGRATION_COMPOSE) up -d --wait

.PHONY: db-check-combined-postgres-down
db-check-combined-postgres-down: ## stop and wipe the PostgreSQL container for combined migration checks
	docker compose -f $(MIGRATION_COMPOSE) down -v

.PHONY: db-check-combined-sqlite
db-check-combined-sqlite: ## upgrade control-plane, knowledge-flow, and fred-runtime against the same SQLite DB, check for drift, then downgrade
	@echo "=== Combined SQLite migration check: upgrade ==="
	@rm -f $(SQLITE_COMBINED_DB)
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(CP_UV) run --directory apps/control-plane-backend alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(KF_UV) run --directory apps/knowledge-flow-backend alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory libs/fred-runtime alembic upgrade head
	@echo "=== Combined SQLite migration check: drift check ==="
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(CP_UV) run --directory apps/control-plane-backend alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(KF_UV) run --directory apps/knowledge-flow-backend alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory libs/fred-runtime alembic check
	@echo "=== Combined SQLite migration check: downgrade ==="
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(KF_UV) run --directory apps/knowledge-flow-backend alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(CP_UV) run --directory apps/control-plane-backend alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory libs/fred-runtime alembic downgrade base
	@rm -f $(SQLITE_COMBINED_DB)
	@echo "=== Combined SQLite migration check passed ==="

.PHONY: db-check-combined-postgres
db-check-combined-postgres: db-check-combined-postgres-down db-check-combined-postgres-up ## upgrade control-plane, knowledge-flow, and fred-runtime against the same DB, check for drift, then downgrade
	@echo "=== Combined migration check: upgrade ==="
	DATABASE_URL="$(PG_COMBINED_URL)" $(CP_UV) run --directory apps/control-plane-backend alembic upgrade head
	DATABASE_URL="$(PG_COMBINED_URL)" $(KF_UV) run --directory apps/knowledge-flow-backend alembic upgrade head
	DATABASE_URL="$(PG_COMBINED_URL)" $(RT_UV) run --directory libs/fred-runtime alembic upgrade head
	@echo "=== Combined migration check: drift check ==="
	DATABASE_URL="$(PG_COMBINED_URL)" $(CP_UV) run --directory apps/control-plane-backend alembic check
	DATABASE_URL="$(PG_COMBINED_URL)" $(KF_UV) run --directory apps/knowledge-flow-backend alembic check
	DATABASE_URL="$(PG_COMBINED_URL)" $(RT_UV) run --directory libs/fred-runtime alembic check
	@echo "=== Combined migration check: downgrade ==="
	DATABASE_URL="$(PG_COMBINED_URL)" $(KF_UV) run --directory apps/knowledge-flow-backend alembic downgrade base
	DATABASE_URL="$(PG_COMBINED_URL)" $(CP_UV) run --directory apps/control-plane-backend alembic downgrade base
	DATABASE_URL="$(PG_COMBINED_URL)" $(RT_UV) run --directory libs/fred-runtime alembic downgrade base
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
