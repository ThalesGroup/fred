# Postgres Migration: Kea → Swift

Tools for comparing and visualising the database schema changes between the
**Kea** and **Swift** generations of the fred platform.

To start, just open [migration-guide.html](./migration-guide.html) !

## Usage (if need to regenerate data)

### 1. Schema comparison

Requires Docker (uses `scripts/docker-compose.postgres.yml`).

```bash
# Basic run — compares all tables by name
python3 docs/postgres-migration/generate.py

# Declare renamed tables so they are diffed rather than shown as deleted/new
python3 docs/postgres-migration/generate.py \
  --rename session:session_metadata \
  --rename agent:agent_instance
```

Open `docs/postgres-migration/compare-schemas.html` in a browser when done.

### 2. Migration graph

No Docker needed — reads migration files directly.

```bash
python3 docs/postgres-migration/generate_graph.py
```

Open `docs/postgres-migration/graph.html` in a browser when done.

## Backend mapping

| Backend (Kea) | Backend (Swift) |
|---|---|
| `agentic-backend` | split → `control-plane-backend` + `fred-runtime` |
| `control-plane-backend` | `control-plane-backend` |
| `knowledge-flow-backend` | `knowledge-flow-backend` |

Notable table moves: `session` → `session_metadata` (control-plane), `agent` → `agent_instance` (control-plane), `session_history` → `fred-runtime`.

## Files

| File | Purpose |
|---|---|
| `generate.py` | Spins up ephemeral Postgres containers, runs all Alembic migrations for both Kea and Swift, extracts schemas, and writes `migration_data.json`. Also injects the data into `compare-schemas.html` and `migration-guide.html`. |
| `generate_graph.py` | Parses Alembic migration files directly (no DB needed) to build a DAG of revisions per backend, writes `graph_data.json`, and injects into `graph.html`. |
| `compare-schemas.html` | Side-by-side schema diff viewer (same / renamed / deleted / new tables). |
| `migration-guide.html` | Step-by-step migration guide driven by the same data. |
| `graph.html` | Visual DAG of Alembic revision history for each backend in both versions. |
| `migration_data.json` | Generated — schema comparison data (do not edit by hand). |
| `graph_data.json` | Generated — migration DAG data (do not edit by hand). |