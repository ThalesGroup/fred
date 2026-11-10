CODE_QUALITY_DIRS := libs/fred-pod libs/fred-core libs/fred-knowledge libs/fred-sdk libs/fred-runtime libs/capabilities/fred-capability-writable-document libs/capabilities/fred-capability-ppt-filler libs/capabilities/fred-capability-html-artifact libs/capabilities/fred-capability-team-wiki libs/capabilities/fred-capability-documents libs/capabilities/fred-capability-document-access libs/capabilities/fred-capability-web-research libs/frontend apps/fred-agents apps/control-plane apps/knowledge-flow-backend apps/knowledge-flow-worker apps/frontend
TEST_DIRS := libs/fred-pod libs/fred-core libs/fred-knowledge libs/fred-sdk libs/fred-runtime libs/capabilities/fred-capability-writable-document libs/capabilities/fred-capability-ppt-filler libs/capabilities/fred-capability-html-artifact libs/capabilities/fred-capability-team-wiki libs/capabilities/fred-capability-documents libs/capabilities/fred-capability-document-access libs/capabilities/fred-capability-web-research libs/frontend apps/fred-agents apps/control-plane apps/knowledge-flow-backend apps/knowledge-flow-worker apps/frontend
DOCKER_BUILD_DIRS := apps/fred-agents apps/knowledge-flow-backend apps/knowledge-flow-worker apps/control-plane apps/frontend
RUN_DIRS := apps/control-plane apps/fred-agents apps/knowledge-flow-backend apps/knowledge-flow-worker apps/frontend
ENV_APPS := apps/control-plane apps/fred-agents apps/knowledge-flow-backend apps/knowledge-flow-worker

.DEFAULT_GOAL := help

##@ Provisioning

.PHONY: bundle-demo
bundle-demo: ## Generate the Acme/Globex demo bundle offline, without importing it
	$(MAKE) -C apps/control-plane bundle-demo

.PHONY: bundle-migration
bundle-migration: ## Generate the Nova coexistence bundle offline, without importing it
	$(MAKE) -C apps/control-plane bundle-migration

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
code-quality: migration-tests ## Run code quality checks in all submodules
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
test: k3d-tests pod-chart-tests libs-version-tests publish-libs-tests ## Run non-integration test suites in all submodules and print coverage summary
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

.PHONY: validation-report integration-test-docker integration-test-k3d
validation-report: ## Run the live cross-app validation suite (requires infra + running apps - see validation/README.md)
	$(MAKE) -C validation validation-report

integration-test-docker: ## Validate running local Docker-backed services and Fred apps using their direct ports
	$(MAKE) -C validation $@

integration-test-k3d: ## Validate an existing local k3d deployment through its ingress (weaver.localhost:8088)
	$(MAKE) -C validation $@

##@ Setup

.PHONY: delegation
delegation: ## Prepare local delegation after docker-up, without editing tracked YAML (ARGS=--dry-run or --reset)
	uv run scripts/populate_local_delegation.py $(ARGS)

# The local defaults of fred-deployment-factory's Docker Compose services.
LOCAL_PASSWORD := Azerty123_
LOCAL_SECRET_KEYS := FRED_POSTGRES_PASSWORD OPENSEARCH_PASSWORD MINIO_SECRET_KEY \
	KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET KEYCLOAK_AGENTIC_CLIENT_SECRET KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET \
	MANAGER_WORKER_CLIENT_SECRET FRED_CONTENT_SECRET_KEY KF_ARTIFACT_SECRET_KEY MANAGER_DERIVED_SECRET_KEY
WEAVER_DATABASE := fred_weaver
# Fred reaches that PostgreSQL as its applications do, through the published port and never
# by container name. The client runs in the chart hook's image: the host needs no psql.
LOCAL_POSTGRES_HOST := host.docker.internal
LOCAL_POSTGRES_ADMIN := admin
POSTGRES_BOOTSTRAP_IMAGE := pgvector/pgvector:pg15

.PHONY: setup-env
setup-env: ## Create each backend's .env from its .env.template (idempotent) and fill in the local Docker Compose secrets and the model keys exported in the shell (MISTRAL_API_KEY, OPENAI_API_KEY)
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
	@# (Postgres/OpenSearch/S3 passwords, every Keycloak client secret) -- only
	@# ever fills a placeholder that's still literally empty, never overwrites a real value.
	@for dir in $(ENV_APPS); do \
		f="$$dir/config/.env"; \
		[ -f "$$f" ] || continue; \
		for key in $(LOCAL_SECRET_KEYS); do \
			sed -i -E "s/^$$key=(\"\")?$$/$$key=\"$(LOCAL_PASSWORD)\"/" "$$f"; \
		done; \
	done
	@# The root platform-admin bootstrap secret: generated once, at least 16 characters.
	@f=apps/control-plane/config/.env; \
	if grep -qE '^FRED_BOOTSTRAP_TOKEN=("")?$$' "$$f" 2>/dev/null; then \
		sed -i -E "s/^FRED_BOOTSTRAP_TOKEN=(\"\")?$$/FRED_BOOTSTRAP_TOKEN=\"$$(openssl rand -hex 24)\"/" "$$f"; \
		echo "************ Generated FRED_BOOTSTRAP_TOKEN in $$f ************"; \
	fi
	@# knowledge-flow-backend's own .env.template still defaults CONFIG_FILE to configuration.yaml
	@# (doc drift vs. the other two apps) -- only fix it if it's still exactly that stale
	@# template default, never touch a value a developer deliberately set to something else.
	@if [ -f apps/knowledge-flow-backend/config/.env ] && grep -qE '^CONFIG_FILE="?\./config/configuration\.yaml"?$$' apps/knowledge-flow-backend/config/.env; then \
		sed -i 's|^CONFIG_FILE=.*|CONFIG_FILE="./config/configuration_prod.yaml"|' apps/knowledge-flow-backend/config/.env; \
		echo "************ Fixed knowledge-flow-backend CONFIG_FILE to configuration_prod.yaml ************"; \
	fi
	@# Model keys, the same in every application: each one exported in the shell
	@# replaces the one in every .env.
	@for key in MISTRAL_API_KEY OPENAI_API_KEY; do \
		value="$$(printenv $$key || true)"; \
		[ -n "$$value" ] || continue; \
		for dir in $(ENV_APPS); do sed -i -E "s|^$$key=.*|$$key=\"$$value\"|" "$$dir/config/.env"; done; \
		echo "************ $$key copied from the shell ************"; \
	done
	@# The local organizations Acme and Globex use Mistral (apps/control-plane/config/
	@# configuration_prod.yaml): without its key, their provisioning stops at model discovery.
	@grep -qE '^MISTRAL_API_KEY="?[^"]+' apps/control-plane/config/.env \
		|| { echo "Missing MISTRAL_API_KEY: the local organizations Acme and Globex use Mistral. export MISTRAL_API_KEY=..., then rerun." >&2; exit 1; }
	@echo "✓ setup-env done. Review apps/*/config/.env yourself for anything beyond local docker-compose defaults (Azure, proxy, Prometheus, ...)."

.PHONY: docker-prepare
docker-prepare: ## What k3d's install hooks do, against Docker Compose: database roles and schemas, Control Plane schema, worker contract (replayable)
	@# The chart's postgresBootstrap hook: the same image and SQL files, as the administrator.
	cat deploy/postgres/bootstrap.sql deploy/postgres/role-passwords.sql | docker run --rm -i \
		--add-host=host.docker.internal:host-gateway \
		-e PGHOST=$(LOCAL_POSTGRES_HOST) -e PGPORT=5432 -e PGDATABASE=$(WEAVER_DATABASE) \
		-e PGUSER=$(LOCAL_POSTGRES_ADMIN) -e PGPASSWORD=$(LOCAL_PASSWORD) \
		-e PGOPTIONS='-c client_min_messages=warning' \
		$(foreach role,CP KF RUNTIME MONITOR,-e $(role)_PASSWORD=$(LOCAL_PASSWORD)) \
		$(POSTGRES_BOOTSTRAP_IMAGE) psql -X -q -o /dev/null -v ON_ERROR_STOP=1 -v database=$(WEAVER_DATABASE) -f -
	@# Then the chart's migration Jobs.
	DATABASE_URL=postgresql://fred_cp:$(LOCAL_PASSWORD)@localhost:5432/$(WEAVER_DATABASE) \
		$(MAKE) -C apps/control-plane initialize-schema
	$(MAKE) -C apps/knowledge-flow-worker dev
	@mkdir -p apps/control-plane/target
	cd apps/knowledge-flow-worker && .venv/bin/python -m knowledge_flow_worker.features.scheduler.export_contract \
		--configuration config/configuration_worker.yaml > ../control-plane/target/worker-contract.json
	@echo "✓ docker-prepare done."

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
	$(MAKE) -C apps/control-plane run

.PHONY: run
run: ## Start every Fred application, the workers included, in one terminal (Ctrl+C stops them all)
	@set -e; \
	for dir in $(RUN_DIRS); do \
		echo "************ Starting $$dir ************"; \
		$(MAKE) -C $$dir run & \
	done; \
	$(MAKE) -C apps/fred-agents run-worker & \
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

.PHONY: sbom
sbom: ## Generate local image CycloneDX SBOMs (IMAGE=name for one, CVES=true for vulnerabilities)
	@bash scripts/generate_image_sboms.sh

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
PYPI_UV ?= $(shell command -v uv 2>/dev/null)
PYPI_RELEASE_CHECK ?= python3 scripts/validate_python_release.py

# The Python packages published to PyPI, in dependency order: the libs, then
# the capabilities. Each pyproject.toml owns its package version.
PYPI_PACKAGES := \
	libs/fred-pod \
	libs/fred-core \
	libs/fred-knowledge \
	libs/fred-sdk \
	libs/fred-runtime \
	libs/capabilities/fred-capability-document-access \
	libs/capabilities/fred-capability-documents \
	libs/capabilities/fred-capability-html-artifact \
	libs/capabilities/fred-capability-mcp \
	libs/capabilities/fred-capability-ppt-filler \
	libs/capabilities/fred-capability-team-wiki \
	libs/capabilities/fred-capability-web-research \
	libs/capabilities/fred-capability-writable-document

# Fred's generic pod charts, released with the fred chart.
POD_CHARTS := agent-pod knowledge-base

BASE_TAG ?=
CAPABILITY_PACKAGES ?=
CAPABILITY_MANIFESTS ?=
POD_CHANGED ?= false
PYTHON_RELEASE_ARGS = --base "$(BASE_TAG)" $(foreach name,$(CAPABILITY_PACKAGES),--capability "$(name)") $(foreach path,$(CAPABILITY_MANIFESTS),--manifest "$(path)") $(if $(filter true,$(POD_CHANGED)),--pod,)

.PHONY: python-release-plan prepare-python-release
python-release-plan: ## Show patch versions and changed capability candidates (BASE_TAG=code/vX.Y.Z)
	@test -n "$(BASE_TAG)" || { echo "BASE_TAG is required."; exit 1; }
	python3 scripts/libs_version.py plan $(PYTHON_RELEASE_ARGS)

prepare-python-release: ## Patch selected Python packages/manifests and relock affected projects
	@test -n "$(BASE_TAG)" || { echo "BASE_TAG is required."; exit 1; }
	python3 scripts/libs_version.py apply $(PYTHON_RELEASE_ARGS)

.PHONY: libs-version-tests
libs-version-tests: ## Test independent Python release preparation offline
	python3 -m unittest discover -s scripts/tests -p 'test_libs_version.py'

.PHONY: publish-libs-tests
publish-libs-tests: ## Test bulk publishing offline with fake packages
	python3 -m unittest discover -s scripts/tests -p 'test_publish_libs.py'

# PyPI is the reference, not a tag: releases may skip a publication. A package
# whose version is above PyPI's latest is uploaded; one at PyPI's latest must
# build the published wheel, or its version was not raised and nothing is
# uploaded. The check needs every package built, so each target builds them all.
.PHONY: _build-libs
_build-libs:
	@test -n "$(PYPI_UV)" || { echo "uv is required to build the PyPI packages."; exit 1; }
	@set -e; \
	for dir in $(PYPI_PACKAGES); do \
		echo "************ Building $$dir ************"; \
		env -u VIRTUAL_ENV $(MAKE) -C $$dir UV="$(PYPI_UV)" publish-dry-run; \
		done

.PHONY: publish-libs-dry-run
publish-libs-dry-run: ## Build every PyPI package in order and check it against PyPI, upload nothing
	@$(MAKE) --no-print-directory _build-libs
	@$(MAKE) --no-print-directory validate-python-release

.PHONY: validate-python-release
validate-python-release: ## Check the built PyPI packages against PyPI: what is new, and that nothing changed under a published version
	$(PYPI_RELEASE_CHECK) --pypi $(PYPI_PACKAGES) >/dev/null

.PHONY: publish-libs
publish-libs: ## Build, check against PyPI, then upload in order the packages with a new version (requires PYPI_TOKEN)
	@test -n "$$PYPI_TOKEN" || { echo "PYPI_TOKEN is not set: nothing was built or uploaded."; exit 1; }
	@$(MAKE) --no-print-directory _build-libs
	@set -e; \
	pending=$$($(PYPI_RELEASE_CHECK) --pypi $(PYPI_PACKAGES)); \
	for dir in $$pending; do \
		echo "************ Publishing $$dir ************"; \
		env -u VIRTUAL_ENV $(MAKE) -C $$dir UV="$(PYPI_UV)" publish; \
	done; \
	echo "Every PyPI package is published."

.PHONY: set-version
set-version: ## Update the chart and application versions; Python packages have prepare-python-release (usage: make set-version VERSION=x.y.z)
	@if [ -z "$(VERSION)" ]; then echo "ERROR: VERSION is required. Usage: make set-version VERSION=x.y.z"; exit 1; fi
	$(eval PY_VERSION := $(shell echo "$(VERSION)" | sed 's/-/+/'))
	@echo "Setting version to $(VERSION) (Python: $(PY_VERSION))..."
	@echo "--- Helm chart ---"
	sed -i 's/^version: .*/version: $(VERSION)/' deploy/charts/fred/Chart.yaml
	sed -i 's/^appVersion: .*/appVersion: $(VERSION)/' deploy/charts/fred/Chart.yaml
	sed -i 's/^version: .*/version: $(VERSION)/' $(POD_CHARTS:%=deploy/charts/%/Chart.yaml)
	@echo "--- fred-agents ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' apps/fred-agents/pyproject.toml
	cd apps/fred-agents && uv lock
	@echo "--- knowledge-flow-backend ---"
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' apps/knowledge-flow-backend/pyproject.toml
	cd apps/knowledge-flow-backend && uv lock
	sed -i 's/^version = .*/version = "$(PY_VERSION)"/' apps/knowledge-flow-worker/pyproject.toml
	cd apps/knowledge-flow-worker && uv lock
	@echo "--- frontend ---"
	cd apps/frontend && npm version $(VERSION) --no-git-tag-version
	@echo "Version updated to $(VERSION) in all components."

##@ Database Migrations (combined)

MIGRATION_COMPOSE    := scripts/docker-compose.postgres.yml
FRED_MIGRATION_PG_PORT ?= 5433
export FRED_MIGRATION_PG_PORT
PG_COMBINED_URL      := postgresql+asyncpg://fred_runtime:test@localhost:$(FRED_MIGRATION_PG_PORT)/test_migrations
PG_COMBINED_ADMIN    := postgresql+asyncpg://test:test@localhost:$(FRED_MIGRATION_PG_PORT)/test_migrations
MIGRATION_CARGO      ?= cargo
SQLITE_COMBINED_DB   := /tmp/fred_combined_migrations.db
# One entry per Alembic tree. These lists are hardcoded, not discovery: a new
# tree is exercised by nothing until it is added to all three targets below.
RT_DIR               := libs/fred-runtime
WD_DIR               := libs/capabilities/fred-capability-writable-document
PB_DIR               := libs/capabilities/fred-capability-ppt-filler
RT_UV                := $(RT_DIR)/.venv/bin/uv
WD_UV                := $(WD_DIR)/.venv/bin/uv
PB_UV                := $(PB_DIR)/.venv/bin/uv

.PHONY: db-check-combined-heads
db-check-combined-heads: ## assert each Alembic tree has exactly one head (no branch conflicts)
	$(MAKE) -C $(RT_DIR) db-check-heads
	$(MAKE) -C $(WD_DIR) db-check-heads
	$(MAKE) -C $(PB_DIR) db-check-heads

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
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory $(RT_DIR) alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(WD_UV) run --directory $(WD_DIR) alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(PB_UV) run --directory $(PB_DIR) alembic upgrade head
	@echo "=== Combined SQLite migration check: drift check ==="
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory $(RT_DIR) alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(WD_UV) run --directory $(WD_DIR) alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(PB_UV) run --directory $(PB_DIR) alembic check
	@echo "=== Combined SQLite migration check: downgrade ==="
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(PB_UV) run --directory $(PB_DIR) alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(WD_UV) run --directory $(WD_DIR) alembic downgrade base
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_COMBINED_DB)" $(RT_UV) run --directory $(RT_DIR) alembic downgrade base
	@rm -f $(SQLITE_COMBINED_DB)
	@echo "=== Combined SQLite migration check passed ==="

.PHONY: db-check-combined-postgres
db-check-combined-postgres: db-check-combined-postgres-down db-check-combined-postgres-up ## verify the real CP root, runtime migrations and concurrent cascades
	@set -e; trap '$(MAKE) db-check-combined-postgres-down' EXIT; \
	docker compose -f $(MIGRATION_COMPOSE) exec -T postgres psql -X -v ON_ERROR_STOP=1 -v database=test_migrations -U test -d test_migrations < deploy/postgres/bootstrap.sql; \
	docker compose -f $(MIGRATION_COMPOSE) exec -T postgres psql -X -v ON_ERROR_STOP=1 -U test -d test_migrations -c "ALTER ROLE fred_cp PASSWORD 'test'; ALTER ROLE fred_runtime PASSWORD 'test'"; \
	DATABASE_URL="postgresql://fred_cp:test@localhost:$(FRED_MIGRATION_PG_PORT)/test_migrations" $(MIGRATION_CARGO) run --locked -p control-plane -- initialize-schema; \
	DATABASE_URL="$(PG_COMBINED_URL)" DATABASE_SCHEMA=runtime $(RT_UV) run --directory $(RT_DIR) alembic upgrade head; \
	DATABASE_URL="$(PG_COMBINED_URL)" DATABASE_SCHEMA=runtime $(WD_UV) run --directory $(WD_DIR) alembic upgrade head; \
	DATABASE_URL="$(PG_COMBINED_URL)" DATABASE_SCHEMA=runtime $(PB_UV) run --directory $(PB_DIR) alembic upgrade head; \
	DATABASE_URL="$(PG_COMBINED_URL)" DATABASE_SCHEMA=runtime $(RT_UV) run --directory $(RT_DIR) alembic check; \
	DATABASE_URL="$(PG_COMBINED_URL)" DATABASE_SCHEMA=runtime $(WD_UV) run --directory $(WD_DIR) alembic check; \
	DATABASE_URL="$(PG_COMBINED_URL)" DATABASE_SCHEMA=runtime $(PB_UV) run --directory $(PB_DIR) alembic check; \
	FRED_TEST_POSTGRES_URL="$(PG_COMBINED_ADMIN)" FRED_TEST_ROLE_PASSWORD=test $(RT_UV) run --directory $(RT_DIR) pytest tests/test_session_ownership.py tests/test_session_filesystem_postgres.py -q

include scripts/makefiles/help.mk
include scripts/makefiles/chart-schema.mk

# k3d: fred-deployment-factory deploys this chart on its local k3d instance
# (`make k3d-up`, then `make k3d-app FRED=weaver APP=fred DIR=<this checkout>`), with the
# images deploy/k3d/build makes from this checkout.

.PHONY: k3d-tests k3d-reset-storage-tests
k3d-tests: ## Test local k3d image preparation and reset safeguards without a cluster
	python3 -m unittest discover -s deploy/k3d -p 'test_*.py'

k3d-reset-storage-tests: ## Verify reset storage operations on disposable Docker services (no k3d mutation)
	RESET_STORAGE_TESTS=1 python3 -m unittest discover -s deploy/k3d -p 'test_reset_storage.py'

.PHONY: pod-chart-tests
pod-chart-tests: ## Render the agent-pod and knowledge-base charts with helm (skipped without helm)
	python3 -m unittest deploy/charts/test_pod_charts.py

##@ Migration notes and release preparation

MIGRATION_BASE ?= origin/swift
MIGRATION_GUIDES = uv run --project libs/fred-pod --locked --no-dev python scripts/migration_guides.py

.PHONY: migration-check release-plan release-guide migration-tests
migration-check: ## Check this PR's migration note, including uncommitted edits
	@$(MIGRATION_GUIDES) check-pr --base "$(MIGRATION_BASE)" --worktree

release-plan: ## Report release impact, minimum version and missing migration notes
	@$(MIGRATION_GUIDES) plan

release-guide: ## Generate and validate the DevOps guide: make release-guide RELEASE_VERSION=X.Y.Z
	@test -n "$(RELEASE_VERSION)" || { echo "Usage: make release-guide RELEASE_VERSION=X.Y.Z"; exit 1; }
	@$(MIGRATION_GUIDES) generate --worktree --version "$(RELEASE_VERSION)"
	@$(MIGRATION_GUIDES) verify --worktree --version "$(RELEASE_VERSION)"

migration-tests: ## Validate release migration tooling offline with synthetic Git histories
	uv run --project libs/fred-pod --locked --no-dev python -m unittest discover -s scripts/tests -p 'test_migration_guides.py' -v

.PHONY: test-knowledge-flow-contracts
test-knowledge-flow-contracts:
	$(MAKE) -C apps/knowledge-flow-worker dev
	PYTHONPATH=$(CURDIR)/validation/knowledge_flow:$(CURDIR)/apps/knowledge-flow-backend:$(CURDIR)/apps/knowledge-flow-worker apps/knowledge-flow-worker/.venv/bin/python -m pytest validation/knowledge_flow/tests --confcutdir=validation/knowledge_flow --allow-hosts=127.0.0.1 --allow-unix-socket
