# Database Migrations

Fred uses [Alembic](https://alembic.sqlalchemy.org/) to manage PostgreSQL schema changes.

Alembic manages schema evolution through migration scripts stored in `alembic/versions/`.
Each script is a Python file with an `upgrade()` and `downgrade()` function that emit the
SQL needed to move the schema forward or backward. Scripts form a linked list: each one
records its own revision ID and the ID of its parent, so Alembic can walk the chain in
order. The current position is tracked in an `alembic_version` table in the database itself.

The `--autogenerate` flag compares the current ORM models against the live database and
drafts the `upgrade()`/`downgrade()` functions automatically.

Each backend that owns database tables has its own Alembic setup under `<backend>/alembic/`.
ORM models are registered in each backend's `alembic/env.py` so that autogenerate can
detect differences between the code and the live database.

## Configuration

Alembic connects to the PostgreSQL instance defined in the config file pointed to by
`CONFIG_FILE`. Locally this defaults to `./config/configuration_prod.yaml`
(set via `ALEMBIC_CONFIG_FILE` in the Makefile).

You can override it:

```bash
make db-upgrade ALEMBIC_CONFIG_FILE=./config/my_config.yaml
```

Alternatively, set the `DATABASE_URL` environment variable to bypass configuration
file loading entirely and connect to an arbitrary database:

```bash
DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/mydb" make db-upgrade
```

## Changing a table definition

1. Edit the SQLAlchemy ORM model (e.g. add a column, create a new table).
2. Generate a migration:

```bash
make db-migrate MSG="add description column to agent"
```

This compares the ORM models against the live database and produces a new file
in `alembic/versions/`.

3. Review the generated migration file. Autogenerate is good but not perfect --
   check that it matches your intent
   (see [autogenerate limitations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect)).
4. Apply the migration:

```bash
make db-upgrade
```

5. Commit both the model change and the migration file together.

## Upgrading a database

Apply all pending migrations:

```bash
make db-upgrade
```

Under the hood: `alembic upgrade head`.

## Downgrading a database

Roll back the last migration:

```bash
make db-downgrade
```

Under the hood: `alembic downgrade -1`.

To roll back to a specific revision, use Alembic directly:

```bash
CONFIG_FILE=./config/configuration_prod.yaml uv run alembic downgrade <revision_id>
```

## Viewing migration history

```bash
make db-history
```

## Onboarding an existing database (no prior Alembic)

Databases created before Alembic was introduced already have the correct tables
but no `alembic_version` entry. To register them without re-running SQL:

```bash
make db-stamp
```

This writes the current head revision into `alembic_version` so that future
migrations apply normally. After stamping, run upgrade to apply any migrations
added since the stamp point:

```bash
make db-upgrade
```

## CI checks

A CI workflow (`Check-migrations.yml`) runs on every PR that touches migration
files or ORM models. It validates migrations against both SQLite and PostgreSQL.

You can run the same checks locally:

```bash
make db-check-migrations
```

This runs four checks:

1. **Single head** -- asserts there is exactly one Alembic head (catches branch conflicts).
2. **SQLite upgrade/check/downgrade** -- validates the full migration chain on a temporary SQLite database.
3. **PostgreSQL upgrade/check/downgrade** -- same validation against a PostgreSQL container
   (started and stopped automatically via `scripts/docker-compose.postgres.yml`).
4. **`alembic check`** -- compares ORM models against the migrated schema to detect forgotten migrations.

Individual checks are also available:

```bash
make db-check-heads          # single head assertion only
make db-check-sqlite         # SQLite checks only
make db-check-postgres-up    # start the PostgreSQL container
make db-check-postgres       # PostgreSQL checks only (assumes container is running)
make db-check-postgres-down  # stop the PostgreSQL container
make db-check-postgres-full  # start container, run checks, stop container
```

## Make targets reference

| Target               | Description                                    |
|----------------------|------------------------------------------------|
| `db-migrate`         | Generate a new migration (`MSG="description"`) |
| `db-upgrade`         | Apply all pending migrations                   |
| `db-downgrade`       | Roll back the last migration                   |
| `db-stamp`           | Mark DB as up-to-date without running SQL      |
| `db-history`         | Show migration history                         |
| `db-check-migrations`   | Run full migration CI check suite              |
| `db-check-heads`        | Assert single Alembic head                     |
| `db-check-sqlite`       | Migration checks against SQLite                |
| `db-check-postgres-up`  | Start PostgreSQL container                     |
| `db-check-postgres`     | Migration checks against PostgreSQL            |
| `db-check-postgres-down`| Stop PostgreSQL container                      |
| `db-check-postgres-full`| Start, check, stop PostgreSQL                  |
