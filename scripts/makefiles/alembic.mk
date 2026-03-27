##@ Database Migrations (Alembic)

ALEMBIC_CONFIG_FILE ?= ./config/configuration_prod.yaml

# Auto-upgrade the database before starting.
run-local: db-upgrade

.PHONY: db-migrate
db-migrate: dev ## generate a new migration revision (usage: make db-migrate MSG="description")
	CONFIG_FILE=$(ALEMBIC_CONFIG_FILE) $(UV) run alembic revision --autogenerate -m "$(MSG)"

.PHONY: db-upgrade
db-upgrade: dev ## apply all pending migrations (alembic upgrade head)
	CONFIG_FILE=$(ALEMBIC_CONFIG_FILE) $(UV) run alembic upgrade head

.PHONY: db-stamp
db-stamp: dev ## stamp an existing database as up-to-date without running SQL (use on first deploy)
	CONFIG_FILE=$(ALEMBIC_CONFIG_FILE) $(UV) run alembic stamp head

.PHONY: db-downgrade
db-downgrade: dev ## roll back the last migration (alembic downgrade -1)
	CONFIG_FILE=$(ALEMBIC_CONFIG_FILE) $(UV) run alembic downgrade -1

.PHONY: db-history
db-history: dev ## show migration history
	CONFIG_FILE=$(ALEMBIC_CONFIG_FILE) $(UV) run alembic history --verbose

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
