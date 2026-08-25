# Database Migrations

Fred uses [Alembic](https://alembic.sqlalchemy.org/) to manage PostgreSQL schema changes.

Alembic manages schema evolution through migration scripts stored in `alembic/versions/`.
Each script is a Python file with an `upgrade()` and `downgrade()` function that emit the
SQL needed to move the schema forward or backward. Scripts form a linked list: each one
records its own revision ID and the ID of its parent, so Alembic can walk the chain in
order. The current position is tracked in an `alembic_version` table in the database itself.

The `--autogenerate` flag compares the current ORM models against the live database and
drafts the `upgrade()`/`downgrade()` functions automatically.

Each component that owns database tables has its own tree, its own version table, and its
own single head — never rebased against another's. ORM models are registered in each tree's
`env.py` so that autogenerate can detect differences between the code and the live database.

| Tree | Location | Version table |
| --- | --- | --- |
| control-plane | `apps/control-plane-backend/alembic/` | `alembic_version_control_plane` |
| knowledge-flow | `apps/knowledge-flow-backend/alembic/` | `alembic_version_knowledge_flow` |
| fred-runtime | `libs/fred-runtime/alembic/` | `alembic_version_runtime` |
| writable-document capability | `libs/fred-capability-writable-document/fred_capability_writable_document/writable_document_migrations/` | `cap_writable_document_alembic_version` |

A capability's tree sits inside its package rather than under `alembic/`, because
`python -m fred_runtime migrate` discovers it by entry point (`fred.capabilities`) and runs
it after fred-runtime's own. Every tree resolves its `script_location` from a
`[tool.alembic]` block in the owning package's `pyproject.toml`, which is also what lets the
`alembic` CLI and the CI checks below reach it.

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

## Who creates tables: Alembic only

No runtime store creates its own tables. `PostgresHistoryStore` used to run
`metadata.create_all` lazily on every read and write path; that produced
databases with the right tables and an *unstamped* version table, which no
later `alembic upgrade head` could ever be applied to (issue #2290). Since
then:

- `session_history` DDL lives only in `libs/fred-runtime/alembic/versions/`;
- a fred-runtime pod verifies at startup that `session_history` exists and
  refuses to finish booting when it does not — the log names the table and the
  command to run, instead of surfacing an `UndefinedTableError` mid-request
  hours later;
- migrations are applied by `python -m fred_runtime migrate` (what the Helm
  migration hook and `make db-upgrade` in `apps/fred-agents` both run);
- tests apply the same migrations to their throwaway SQLite databases through
  `fred_runtime.migrations.upgrade_sqlite_database` (~30ms each), so the suite
  also proves the tree produces a schema a pod can boot against. Only fred-core's
  own unit tests use `fred_core.history.create_history_schema` — that package
  sits below the one owning the tree and cannot import upwards to run it.

`SqlCheckpointer` still self-creates its own (non-Alembic) tables — tracked
separately.

### Recovering a database whose `session_history` was self-created

Symptom: the platform works, but `alembic upgrade head` fails with
`DuplicateTable: relation "session_history" already exists`, because
`alembic_version_runtime` was never written. A pod boot also logs:

```
[SCHEMA] fred-runtime: tables exist but 'alembic_version_runtime' is not stamped
```

Fix: stamp the revision that matches the table you actually have, then upgrade.
Which revision depends on the columns present — check first:

```bash
psql "$DSN" -c '\d session_history'
```

| Columns present                                            | Stamp this revision |
| ---------------------------------------------------------- | ------------------- |
| no `exchange_id`                                            | `a1e2f3c4d5b6`      |
| `exchange_id`, but no `team_id` / `agent_instance_id`       | `b2f3a4e5c6d7`      |
| `exchange_id`, `team_id`, `agent_instance_id` (recent code) | `c3d4b5a6f7e8`      |

```bash
cd libs/fred-runtime
CONFIG_FILE=<your config> uv run alembic stamp <revision from the table above>
```

Then apply everything after that point — from `apps/fred-agents`, so installed
capability trees are upgraded in the same pass:

```bash
cd apps/fred-agents && make db-upgrade      # python -m fred_runtime migrate
```

Stamping writes into `alembic_version_runtime` (fred-runtime's own version
table — every backend and every capability has its own; see
`libs/fred-runtime/alembic/env.py`).

## SQLite compatibility

Migrations must work on both PostgreSQL and SQLite (CI validates both).
Two rules to follow:

### Use `with_variant` for PostgreSQL-specific types

SQLite does not support types like `JSONB` or `TIMESTAMP WITH TIME ZONE`.
Use SQLAlchemy's `with_variant` to pick the right type per dialect.

Common portable types are already defined in `fred_core/models/base.py`
(`JsonColumn`, `TimestampColumn`) -- prefer these in ORM models. In migration
files, apply the same pattern:

```python
from sqlalchemy.dialects import postgresql

jsonb_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(), "sqlite"
)
```

### Use `batch_alter_table` when altering columns

SQLite does not support most `ALTER TABLE` operations (drop column, change type,
add NOT NULL, etc.). Alembic's
[batch mode](https://alembic.sqlalchemy.org/en/latest/batch.html) works around
this by recreating the table behind the scenes:

```python
with op.batch_alter_table("session", schema=None) as batch_op:
    batch_op.add_column(sa.Column("team_id", sa.String(), nullable=True))
    batch_op.alter_column("user_id", existing_type=sa.String(), nullable=False)
```

See `alembic/versions/5c9bc83efbfb_upgrade_session_schema.py` for a full
example.

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

The targets above cover one tree — the one in the directory you run them from. From the
repo root, the `db-check-combined-*` targets run every tree in the table above against a
single shared database, which is what `Check-migrations.yml` invokes:

```bash
make db-check-combined-heads     # one head per tree
make db-check-combined-sqlite    # all trees: upgrade, check, downgrade
make db-check-combined-postgres  # same, against a PostgreSQL container
```

These aggregators are hardcoded lists, not discovery: **a new tree is exercised by nothing
until it is added to all three by hand** (and given its `uv sync` step in the workflow).

## How to stamp DB created before Alembic

### 1 - Export DB state

For each backend, export the tables schema

```sh
# Agent
kubectl exec postgresql-primary-0 -- pg_dump "postgresql://postgres:<PASSWORD>@localhost/fred" --schema-only --no-owner --no-privileges  -t agent -t feedbacks -t '"mcp-server"' -t session -t session_attachments -t session_history -t tasks > fred_prod_agent_schema.sql

# KF
kubectl exec postgresql-primary-0 -- pg_dump "postgresql://postgres:<PASSWORD>@localhost/fred" --schema-only --no-owner --no-privileges -t tag -t resource -t sched_workflow_tasks > fred_prod_kf_schema.sql

# CONTROL PLANE
kubectl exec postgresql-primary-0 -- pg_dump "postgresql://postgres:<PASSWORD>@localhost/fred" --schema-only --no-owner --no-privileges -t teammetadata > fred_prod_cp_schema.sql
```

### 2 - Export table schema for each migration

```sh
 make db-snapshots
```

### 3 - Find the migration your DB is at

For each backend, compare the dump of your DB vs dump of the migrations:

- If you have a perfect match -> stamp on the migration id
- No perfect match -> find the closest one, migrate by hand to the closest one then stamp on the migration id
