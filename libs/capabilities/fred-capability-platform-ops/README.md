# fred-capability-platform-ops

Fred agent capabilities for platform introspection. One package, one
`fred.capabilities` entry point per concern, each independently grantable
(ADMIN_GATED).

## Capabilities

- **`platform_postgres`** (`postgres/`) — read-only SQL over the platform
  database: `postgres_list_tables` (zero-arg discovery) +
  `postgres_run_query(sql)`. Tier B: the credentialed executor is NOT in this
  package — it lives in fred-runtime behind the `PlatformSqlPort` contract
  (fred-sdk), where all read-only enforcement happens.

## Registration

Installing this package *is* the registration: the fred-agents pod
auto-discovers each capability at boot via the `fred.capabilities` entry
points declared in `pyproject.toml`.
