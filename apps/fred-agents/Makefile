include ../../scripts/makefiles/config/INFO-fred-agents.mk


include ../../scripts/makefiles/python-vars.mk
include ../../scripts/makefiles/python-deps.mk
include ../../scripts/makefiles/python-run.mk
include ../../scripts/makefiles/python-code-quality.mk
include ../../scripts/makefiles/python-openapi.mk
include ../../scripts/makefiles/python-config-schema.mk
include ../../scripts/makefiles/python-test.mk
include ../../scripts/makefiles/python-clean.mk
include ../../scripts/makefiles/help.mk

##@ Database Migrations (Alembic)

# Same convention as the other backends (scripts/makefiles/alembic.mk):
# `make run` auto-upgrades the DB first, and `db-upgrade` applies migrations.
# fred-agents can't include alembic.mk itself because it owns NO single alembic
# tree: under the capability model (RFC §7.1) fred-runtime owns one tree and
# every installed capability ships its OWN tree, each versioned under a
# `cap_<id>_alembic_version` table. `python -m fred_runtime migrate` upgrades
# fred-runtime's tree then discovers and upgrades every installed capability's
# tree in one pass — the exact command the Helm migration hook runs on deploy
# (values.yaml `migration.command`). CONFIG_FILE selects the config, exactly as
# for `run` (default ./config/configuration.yaml; `run-prod` exports the prod one).

ALEMBIC_CONFIG_FILE ?=
ALEMBIC_CONFIG_ENV = $(if $(strip $(ALEMBIC_CONFIG_FILE)),CONFIG_FILE=$(ALEMBIC_CONFIG_FILE),)

# Auto-upgrade the database before starting, like the other backends.
run-local: db-upgrade

.PHONY: db-upgrade
db-upgrade: dev ## apply all pending migrations (fred-runtime + every capability tree)
	$(ALEMBIC_CONFIG_ENV) $(UV) run python -m fred_runtime migrate

.PHONY: db-downgrade
db-downgrade: check-migration-tree dev ## roll back one revision in MIGRATION_TREE=runtime or capability:<id>
	$(ALEMBIC_CONFIG_ENV) $(UV) run python -m fred_runtime downgrade "$(MIGRATION_TREE)" -1

.PHONY: check-migration-tree
check-migration-tree:
	@test -n "$(MIGRATION_TREE)" || { echo "Set MIGRATION_TREE=runtime or MIGRATION_TREE=capability:<id>" >&2; exit 2; }

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		--network=$(API_DOCKER_NETWORK) \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: run-docker
run-docker: ## Run fred-agents in Docker (uses host network by default)
	@echo "🚀 Running fred-agents in Docker..."
	docker run --rm -it \
		--name $(API_CONTAINER_NAME) \
		--network $(API_DOCKER_NETWORK) \
		-v $(realpath config):/app/config:ro \
		$(IMAGE_FULL)

.PHONY: docker-run
docker-run: run-docker ## Backward-compatible alias for run-docker

PORT ?= 8000

.PHONY: cli
cli: dev ## Open the interactive CLI for a running agent pod
	ENV_FILE=$(CURDIR)/config/.env VIRTUAL_ENV= $(UV) run fred-agents-cli

# Docker runtime defaults
API_CONTAINER_NAME ?= fred-agents-api
API_DOCKER_NETWORK ?= host
