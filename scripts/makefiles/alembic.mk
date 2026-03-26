##@ Database Migrations (Alembic)

ALEMBIC_CONFIG_FILE ?= ./config/configuration_prod.yaml

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
