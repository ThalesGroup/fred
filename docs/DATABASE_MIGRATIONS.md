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

## Make targets reference

| Target           | Description                                    |
|------------------|------------------------------------------------|
| `db-migrate`     | Generate a new migration (`MSG="description"`) |
| `db-upgrade`     | Apply all pending migrations                   |
| `db-downgrade`   | Roll back the last migration                   |
| `db-stamp`       | Mark DB as up-to-date without running SQL      |
| `db-history`     | Show migration history                         |
