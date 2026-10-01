---
name: psql
description: Query PostgreSQL databases running in the app-postgres Docker container
user-invocable: true
argument-hint: <query or intent>
---

## Fred design constraint

For work on Fred, read and apply [the failure and concurrency policy](../../../AGENTS.md#fred-failure-and-concurrency-design--developer-review-first)
before planning, implementing, or recommending changes. Prefer explicit rejection
over recovery machinery. Never add protection for a failure or concurrency scenario
without the developer's explicit review of that scenario and its complexity. This
policy takes precedence over defensive or resilience recommendations below.

# PostgreSQL CLI Skill

You help the user query and inspect the PostgreSQL databases running in the local dev stack.

## Connection

PostgreSQL runs in the **`app-postgres`** Docker container (image: `pgvector/pgvector:pg15`, port `5432`).

Always connect via `docker exec` to avoid host `psql` version mismatches:

```bash
docker exec -it app-postgres psql -U admin -d <database>
```

**Default dev credentials** (used internally by the container — no password prompt needed with `docker exec`):
- User: `admin`
- Password: `Azerty123_`

## Available databases

| Database             | Owner            | Notes                        |
|----------------------|------------------|------------------------------|
| `fred`               | fred             | Main application database    |
| `data`               | tabular          | Tabular data                 |
| `keycloak`           | keycloak_db_user | Auth / identity              |
| `langfuse`           | langfuse         | LLM observability            |
| `openfga`            | openfga          | Authorization tuples         |
| `temporal`           | temporal         | Workflow engine              |
| `temporal_visibility`| temporal         | Temporal visibility store    |
| `postgres`           | admin            | Default admin database       |

## Quick reference

```bash
# List all databases
docker exec app-postgres psql -U admin -l

# List tables in a database
docker exec app-postgres psql -U admin -d fred -c "\dt"

# Describe a table
docker exec app-postgres psql -U admin -d fred -c "\d <table_name>"

# Run a query
docker exec app-postgres psql -U admin -d fred -c "SELECT * FROM <table> LIMIT 10;"
```

## Handling `$ARGUMENTS`

Parse the user's intent from `$ARGUMENTS`. When no database is specified, default to `fred`. Examples:

- `/psql list tables` → `docker exec app-postgres psql -U admin -d fred -c "\dt"`
- `/psql show users` → query the users/accounts table in the `fred` database
- `/psql SELECT * FROM agents LIMIT 5` → run that query against `fred`
- `/psql list tables in langfuse` → `docker exec app-postgres psql -U admin -d langfuse -c "\dt"`

Always use `docker exec app-postgres psql -U admin` (no `-it` flag in non-interactive mode).

For multi-line or complex queries, pass them via `--command` or pipe through `echo`:

```bash
docker exec app-postgres psql -U admin -d fred --command "
  SELECT id, name, created_at
  FROM agents
  ORDER BY created_at DESC
  LIMIT 20;
"
```

## Notes

- The container image includes `pgvector` — vector columns (`embedding vector(...)`) are normal.
- For schema context, check migration files under `apps/<backend-name>/alembic/versions/`
