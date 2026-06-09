# RFC — Postgres-Native ReBAC Backend as OpenFGA Drop-In

**ID:** (to assign — experimental branch `1702-experiment-postgres-native-rebac-backend-as-openfga-drop-in`)  
**Status:** experimental — under validation  
**Author:** Dimitri Tombroff  
**Date:** 2026-06-09  

---

## 1. Problem

Fred's relationship-based access control (ReBAC) currently requires an **OpenFGA sidecar** in every deployment.  
This adds operational cost:

- One more container to deploy, configure, secure, and monitor.
- A bearer token (`OPENFGA_API_TOKEN`) to provision and rotate.
- OpenFGA's internal store (SQLite by default, Postgres for production) runs **beside** Fred's Postgres — two databases for data that is logically part of the same application.
- TLS, health checks, and readiness probes for an extra HTTP endpoint.
- Upgrade coordination: OpenFGA schema changes must be synchronised with Fred releases.

For most Fred deployments, the authorization graph is small (< 50 K tuples) and latency requirements are modest.  
The full Zanzibar/Zookies consistency guarantees that OpenFGA targets are not required.

---

## 2. Proposed Solution

Implement a second `RebacEngine` backend — `PostgresRebacEngine` — that stores tuples in the **existing Fred Postgres database** and evaluates permissions in-process using a Python graph traversal.

The two backends are **drop-in interchangeable**: callers only ever see `RebacEngine`. Switching is a single config-file change.

### 2.1 Storage

A single table is created on startup (idempotent):

```sql
CREATE TABLE IF NOT EXISTS rebac_tuples (
    subject_type VARCHAR(64)  NOT NULL,
    subject_id   VARCHAR(512) NOT NULL,
    relation     VARCHAR(64)  NOT NULL,
    object_type  VARCHAR(64)  NOT NULL,
    object_id    VARCHAR(512) NOT NULL,
    PRIMARY KEY (subject_type, subject_id, relation, object_type, object_id)
);

CREATE INDEX IF NOT EXISTS idx_rebac_by_object
    ON rebac_tuples(object_type, object_id, relation);
```

Every OpenFGA tuple `(user:alice, owner, tag:invoices)` becomes one row.

### 2.2 Permission evaluation

For each request:

1. All stored tuples are fetched from Postgres.
2. Per-request **contextual tuples** (user's Keycloak group memberships and org role, derived from the JWT) are merged in.
3. An in-memory directed graph is built (`_Graph`).
4. The fixed Fred authorization schema is evaluated by Python traversal — no external HTTP call.

The schema rules are transcribed verbatim from `schema.fga`:

| Rule | Implementation |
|---|---|
| `team.owner = [user] or admin from organization` | `_team_owner()` |
| `team.member = [user] or manager` | `_team_member()` |
| `tag.read = viewer or editor or owner or read from parent or member from owner` | `_tag_read()` with cycle guard |
| `document.read = read from parent` | `_tag_read()` on parent tag |
| etc. | … |

Contextual tuples (ephemeral, per-request) are never persisted — same model as OpenFGA.

### 2.3 Known trade-off

This implementation loads **all** tuples per request (O(n) DB fetch).  
For < 50 K tuples this is well under 10 ms.  
A production-hardened version would replace the full fetch with targeted recursive CTEs per permission type.  
That optimisation is explicitly deferred to a follow-up iteration.

---

## 3. Configuration

### 3.1 Switching to Postgres ReBAC

In your `configuration.yaml` (or equivalent), change the `security.rebac` block:

```yaml
security:
  rebac:
    type: postgres                   # ← this line is the only switch
    postgres:
      host: app-postgres             # same host as the rest of the app
      port: 5432
      database: fred
      username: fred
      # password comes from the FRED_POSTGRES_PASSWORD environment variable
    create_table_if_needed: true     # default: true — safe to leave on
```

No other change is needed. The `rebac_tuples` table is created automatically on first startup.

> **Note:** you do not need to set `OPENFGA_API_TOKEN` when using `type: postgres`.  
> The OpenFGA container can be removed from the deployment.

### 3.2 Keeping OpenFGA (existing behaviour, unchanged)

```yaml
security:
  rebac:
    type: openfga                    # ← original value
    api_url: "http://app-fga:9080"
    store_name: "fred"
    create_store_if_needed: true
    sync_schema_on_init: true
    token_env_var: "OPENFGA_API_TOKEN"
```

Nothing changed in the OpenFGA engine. Both backends co-exist; the `type` discriminator selects one.

### 3.3 Disabling ReBAC entirely (existing behaviour, unchanged)

```yaml
security:
  rebac:
    enabled: false
```

### 3.4 Local development with SQLite (postgres backend only)

The Postgres config accepts a `sqlite_path` fallback (same as all other Fred stores):

```yaml
security:
  rebac:
    type: postgres
    postgres:
      sqlite_path: /tmp/fred_rebac_dev.db
```

This requires no running database container and is suitable for offline developer laptops.

### 3.5 Full annotated reference

```yaml
security:
  rebac:
    # ── selector ──────────────────────────────────────────────────────
    type: postgres              # "openfga" | "postgres"

    # ── postgres-specific ─────────────────────────────────────────────
    enabled: true               # set false to bypass all ReBAC checks
                                # (warning: all private resources become public)

    create_table_if_needed: true
                                # creates rebac_tuples + index on startup
                                # idempotent — safe to leave enabled

    postgres:
      # Standard PostgresStoreConfig — same fields used elsewhere in Fred
      host: app-postgres
      port: 5432
      database: fred
      username: fred
      # password: from FRED_POSTGRES_PASSWORD env var (or set inline for dev)

      # SQLite fallback for local development (no Postgres needed)
      # sqlite_path: ~/.fred/rebac.db

      # Optional connection pool tuning
      # pool_size: 5
      # max_overflow: 10
      # pool_timeout: 30
      # pool_recycle: 3600
      # pool_pre_ping: true
      # echo: false           # set true to log every SQL query
```

---

## 4. Migration from OpenFGA to Postgres

There is **no automatic data migration**.  
Team ownership and resource sharing tuples currently stored in OpenFGA must be re-written via the normal Fred APIs after switching.

This is acceptable for most deployments because:
- Persistent tuples (owner/manager/member on teams, owner/editor/viewer on tags) are small in count.
- They can be recreated by the post-install bootstrap script that is already required per `REBAC.md`.
- User-to-team memberships are ephemeral (contextual tuples) and need no migration.

If a lossless migration is required, export tuples from OpenFGA using the Read API and replay them through Fred's admin endpoints before cutting over.

---

## 5. Alternatives Considered

| Alternative | Why not chosen |
|---|---|
| Keep OpenFGA, improve deployment | Doesn't remove the operational dependency |
| Implement permission checks as recursive SQL CTEs | Correct and scalable, but complex to maintain; deferred to follow-up |
| Use SpiceDB or Ory Keto instead | Same external-service problem |
| Build a full Zanzibar-compatible engine | Far exceeds the actual consistency requirements |

---

## 6. Impact on Existing Contracts

| Contract | Impact |
|---|---|
| `RebacEngine` abstract interface | **No change** — both backends implement the same interface |
| OpenFGA engine | **No change** — fully preserved |
| `SecurityConfiguration` | **Additive** — new `type: "postgres"` discriminator value |
| `OPENFGA_API_TOKEN` env var | Not required when using `type: postgres` |
| Fred authorization schema (`schema.fga`) | Not changed — same rules, different evaluator |
| Integration tests | Extended — same test suite now runs against both backends |

---

## 7. Files Changed

| File | Change |
|---|---|
| `libs/fred-core/fred_core/security/rebac/postgres_engine.py` | New — engine implementation |
| `libs/fred-core/fred_core/security/structure.py` | Added `PostgresRebacConfig` |
| `libs/fred-core/fred_core/security/rebac/rebac_factory.py` | Added `postgres` branch |
| `libs/fred-core/fred_core/__init__.py` | Exported new types |
| `libs/fred-core/fred_core/tests/integration/test_rebac.py` | Added `postgres` scenario |
| `libs/fred-core/docker-compose.integration.yml` | Added Postgres service |
