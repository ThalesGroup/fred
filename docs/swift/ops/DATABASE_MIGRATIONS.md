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

> **One chain per database, not per backend.** Alembic opens exactly one connection per
> `env.py`, so a backend that owns tables in two databases needs two chains.
> `knowledge-flow-backend` is the one such backend today (OPS-04, issue #2170):
>
> | Chain | Config | Database | Tables | Version table |
> | --- | --- | --- | --- | --- |
> | `alembic/` | `pyproject.toml` `[tool.alembic]` | shared `fred` | `resource`, `tag`, `metadata` | `alembic_version_knowledge_flow` |
> | `alembic_tasks/` | `alembic_tasks.ini` | dedicated `knowledge_flow` | `task_run`, `task_event_log` | `alembic_version_knowledge_flow_tasks` |
>
> `make db-upgrade` runs the first; **`make db-upgrade-tasks` runs the second**. Upgrading
> only the first leaves the task database un-migrated. The task chain refuses to run when
> `storage.task_postgres` is unset, rather than falling back to the shared database where
> control-plane owns those tables.
>
> The task chain has its own targets, but **not** a twin of every `db-*` target, and the
> two naming shapes differ — operational targets take a `-tasks` suffix, check targets
> infix it:
>
> | Shared chain | Task chain |
> | --- | --- |
> | `db-upgrade` | `db-upgrade-tasks` |
> | `db-migrate` | `db-migrate-tasks` |
> | `db-downgrade` | `db-downgrade-tasks` |
> | `db-history` | `db-history-tasks` |
> | `db-check-heads` | `db-check-**tasks**-heads` |
> | `db-check-sqlite` | `db-check-**tasks**-sqlite` |
> | `db-check-postgres` | `db-check-**tasks**-postgres` |
> | `db-stamp`, `db-snapshots`, `db-check-migrations`, `db-check-postgres-full` | *no equivalent* |
>
> `db-stamp` has no twin deliberately: it registers a database that predates Alembic, and
> the task database is always created by the chain itself. Note `make db-check-migrations`
> covers only the shared chain — CI exercises the task chain through the repo-root
> `db-check-combined-heads` / `db-check-combined-sqlite` targets instead.
>
> Each chain must pass a `MetaData` scoped to the tables it owns, built with
> `Table.to_metadata()` — `fred_core`'s declarative `Base` is a single registry shared by
> every backend, and Alembic applies its name filters only to the connection side, never
> to the metadata side. See `libs/fred-runtime/alembic/env.py` for the reference pattern.
>
> The same split applies to the **boot path**, not just to Alembic: `knowledge-flow`'s
> `main.py` creates the task tables against the task engine and every other `CoreBase`
> table against the shared engine. A single `create_all(CoreBase.metadata)` on the shared
> engine — what it did before OPS-04 — recreates `task_run`/`task_event_log` in `fred` on
> the next restart, undoing the split no matter what the migrations did.

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

---

## Moving existing task rows into the Knowledge Flow task database (OPS-04, issue #2170)

Enabling `storage.task_postgres` only changes where rows are written **from then on**. Rows
already in the shared `fred` database stay there: invisible to Knowledge Flow's `GET /tasks`,
still returned by control-plane's, and never reached by Knowledge Flow's reconciliation
sweeper — so a non-terminal row stranded there stays non-terminal forever.

This procedure moves them. It is operator-driven and deliberately not automated: the fred-core
task tables carry **no per-service discriminator** (that is the premise of #2170), so nothing
in the schema can tell you which rows belong to which backend.

### Step 1 — decide the allowlist, do not assume it

`kind` is the only usable signal. As of this writing the production emitters are:

| `kind` | Emitted by |
|---|---|
| `ingestion` | **Knowledge Flow** (control-plane references it in tests only) |
| `migration`, `erasure` | control-plane |
| `evaluation` | the evaluation backend (its own database) |
| `log` | declared in fred-core, emitted by no application |

**Verify against your own data before trusting that table** — a `kind` added after this was
written lands in the wrong bucket silently:

```sql
SELECT kind, state, count(*) FROM task_run GROUP BY kind, state ORDER BY 1,2;
```

Everything below uses `kind IN ('ingestion')`. Widen it only for kinds you have confirmed are
Knowledge Flow's. Getting this wrong moves control-plane's rows out of its own database.

### Step 2 — quiesce

Stop ingestion and let non-terminal `task_run` rows reach a terminal state. A task whose
`task_run` row moves while its worker is still emitting events raises `TaskNotFoundError`,
which fails the Temporal activity and the workflow with it.

### Step 3 — copy (both databases, one admin role)

The `knowledge_flow` role cannot connect to `fred` by design, so run this as the Postgres
admin. Three details are not optional:

- **Explicit column lists on both sides.** `\copy` is positional and the column *ordinals
  differ* between the two databases — a bare `\copy task_run` silently writes values into the
  wrong columns.
- **`id` is omitted from `task_event_log`.** It is a generated column; copying it drags the
  source values in without advancing the target sequence, and the next insert collides.
- **`task_run` before `task_event_log`**, and delete in the reverse order.

```bash
RUN_COLS="task_id,kind,state,seq,progress,step,detail,error,target,execution_id,created_by,team_id,scheduled_for,created_at,updated_at,acknowledged_at,acknowledged_by"
EVT_COLS="task_id,kind,seq,state,progress,step,detail,error,target,owner,emitted_at"

psql -U admin -d fred -Atc \
  "\\copy (SELECT $RUN_COLS FROM task_run WHERE kind IN ('ingestion')) TO STDOUT WITH (FORMAT csv)" > mv_task_run.csv
psql -U admin -d fred -Atc \
  "\\copy (SELECT $EVT_COLS FROM task_event_log WHERE task_id IN (SELECT task_id FROM task_run WHERE kind IN ('ingestion'))) TO STDOUT WITH (FORMAT csv)" > mv_task_event_log.csv

psql -U admin -d knowledge_flow -c "\\copy task_run ($RUN_COLS) FROM STDIN WITH (FORMAT csv)" < mv_task_run.csv
psql -U admin -d knowledge_flow -c "\\copy task_event_log ($EVT_COLS) FROM STDIN WITH (FORMAT csv)" < mv_task_event_log.csv
```

### Step 4 — verify BEFORE deleting

Counts must match what you extracted, and the sequence must be healthy:

```sql
-- in knowledge_flow
SELECT kind, state, count(*) FROM task_run GROUP BY 1,2 ORDER BY 1,2;
SELECT count(*) FROM task_event_log;
-- ids must be freshly assigned, not the source values
SELECT min(id), max(id) FROM task_event_log;
```

Do not proceed until these are right. The copy is idempotent to re-run only if you truncate
the target first — re-running it as-is duplicates rows.

### Step 5 — delete from the shared database

```sql
-- events first: they reference task_run
DELETE FROM task_event_log
 WHERE task_id IN (SELECT task_id FROM task_run WHERE kind IN ('ingestion'));
DELETE FROM task_run WHERE kind IN ('ingestion');
```

Reconcile: `fred` should retain exactly the other backends' kinds, and the two databases'
combined counts should equal what you started with.

> Verified end-to-end against a clean local stack (2026-08-02): 3 `task_run` rows
> (2 `ingestion`, 1 `migration`) and 4 events in `fred` → 2 rows + 3 events moved to
> `knowledge_flow` with event ids reassigned from 1 and the sequence still healthy, the
> `migration` row and its event untouched in `fred`, no row lost or duplicated.
