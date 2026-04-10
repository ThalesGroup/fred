##@ Database Migrations (Alembic)

ALEMBIC_CONFIG_FILE ?=
ALEMBIC_CONFIG_ENV = $(if $(strip $(ALEMBIC_CONFIG_FILE)),CONFIG_FILE=$(ALEMBIC_CONFIG_FILE),)

# Auto-upgrade the database before starting.
run-local: db-upgrade

.PHONY: db-migrate
db-migrate: dev ## generate a new migration revision (usage: make db-migrate MSG="description")
	$(ALEMBIC_CONFIG_ENV) $(UV) run alembic revision --autogenerate -m "$(MSG)"

.PHONY: db-upgrade
db-upgrade: dev ## apply all pending migrations (alembic upgrade head)
	$(ALEMBIC_CONFIG_ENV) $(UV) run alembic upgrade head

.PHONY: db-stamp
db-stamp: dev ## stamp an existing database as up-to-date without running SQL (use on first deploy)
	$(ALEMBIC_CONFIG_ENV) $(UV) run alembic stamp head

.PHONY: db-downgrade
db-downgrade: dev ## roll back the last migration (alembic downgrade -1)
	$(ALEMBIC_CONFIG_ENV) $(UV) run alembic downgrade -1

.PHONY: db-history
db-history: dev ## show migration history
	$(ALEMBIC_CONFIG_ENV) $(UV) run alembic history --verbose

##@ Migration CI Checks

MIGRATION_COMPOSE := $(CURDIR)/../scripts/docker-compose.postgres.yml
SQLITE_TEST_DB   := $(TARGET)/test_migrations.db
PG_TEST_URL      := postgresql+asyncpg://test:test@localhost:5433/test_migrations

.PHONY: db-check-heads
db-check-heads: dev ## assert there is exactly one Alembic head (no branch conflicts)
	@echo "Checking for single Alembic head..."
	@heads=$$(DATABASE_URL="sqlite+aiosqlite:///unused" $(UV) run alembic heads | grep -c '(head)'); \
	if [ "$$heads" -ne 1 ]; then \
		echo "Expected 1 head, found $$heads"; exit 1; \
	fi
	@echo "Single head confirmed."

.PHONY: db-check-sqlite
db-check-sqlite: dev ## run migration checks against a temporary SQLite database
	@echo "SQLite migration checks..."
	@mkdir -p $(TARGET)
	@rm -f $(SQLITE_TEST_DB)
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_TEST_DB)" $(UV) run alembic upgrade head
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_TEST_DB)" $(UV) run alembic check
	DATABASE_URL="sqlite+aiosqlite:///$(SQLITE_TEST_DB)" $(UV) run alembic downgrade base
	@rm -f $(SQLITE_TEST_DB)
	@echo "SQLite migration checks passed."

.PHONY: db-check-postgres-up
db-check-postgres-up: ## start the PostgreSQL container for migration checks
	docker compose -f $(MIGRATION_COMPOSE) up -d --wait

.PHONY: db-check-postgres-down
db-check-postgres-down: ## stop the PostgreSQL container for migration checks
	docker compose -f $(MIGRATION_COMPOSE) down -v

.PHONY: db-check-postgres
db-check-postgres: dev ## run migration checks against PostgreSQL (assumes container is running)
	@echo "PostgreSQL migration checks..."
	DATABASE_URL="$(PG_TEST_URL)" $(UV) run alembic upgrade head
	DATABASE_URL="$(PG_TEST_URL)" $(UV) run alembic check
	DATABASE_URL="$(PG_TEST_URL)" $(UV) run alembic downgrade base
	@echo "PostgreSQL migration checks passed."

.PHONY: db-check-postgres-full
db-check-postgres-full: db-check-postgres-up db-check-postgres ## start container, run PostgreSQL checks, then stop
	$(MAKE) db-check-postgres-down

.PHONY: db-check-migrations
db-check-migrations: db-check-heads db-check-sqlite db-check-postgres-full ## full migration check suite (heads + SQLite + PostgreSQL)
	@echo "All migration checks passed."

##@ Migration Schema Snapshots

DB_SNAPSHOTS_DIR ?= $(TARGET)/migration-snapshots

.PHONY: db-snapshots
db-snapshots: dev db-check-postgres-up ## dump the schema after each migration revision into $(TARGET)/migration-snapshots/<backend>_<index>_<rev>.sql
	@echo "=== Snapshotting migrations for $(PROJECT_NAME) into $(DB_SNAPSHOTS_DIR) ==="
	@mkdir -p $(DB_SNAPSHOTS_DIR)
	@oldest_first=$$(DATABASE_URL="$(PG_TEST_URL)" $(UV) run alembic history | awk '{print $$3}' | tr -d ',' | tac); \
	idx=1; \
	for rev in $$oldest_first; do \
		echo "--- Upgrading to $$rev (index $$idx) ---"; \
		DATABASE_URL="$(PG_TEST_URL)" $(UV) run alembic upgrade $$rev; \
		out=$(DB_SNAPSHOTS_DIR)/$(PROJECT_NAME)_$$idx\_$$rev.sql; \
		docker compose -f $(MIGRATION_COMPOSE) exec -T postgres \
			pg_dump --schema-only --no-owner --no-acl \
			--exclude-table=alembic_version \
			-U test test_migrations \
			> $$out; \
		echo "  Saved $$out"; \
		idx=$$((idx + 1)); \
	done
	@DATABASE_URL="$(PG_TEST_URL)" $(UV) run alembic downgrade base
	$(MAKE) db-check-postgres-down
	@echo "=== Snapshots done. Compare with: diff <actual_dump.sql> $(DB_SNAPSHOTS_DIR)/$(PROJECT_NAME)_<index>_<rev>.sql ==="
