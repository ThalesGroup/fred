# fred-capability-platform-ops

Fred agent capabilities for platform introspection — the admin-ops family
(`docs/swift/rfc/ADMIN-OPS-AGENTS-RFC.md`). One package, one
`fred.capabilities` entry point per concern, each independently grantable
(ADMIN_GATED).

## Capabilities

- **`platform_postgres`** (`postgres/`) — read-only SQL over the platform
  database: `postgres_list_tables` (zero-arg discovery) +
  `postgres_run_query(sql)`. Tier B: the credentialed executor is NOT in this
  package — it lives in fred-runtime behind the `PlatformSqlPort` contract
  (fred-sdk), where all read-only enforcement happens. Spec:
  `docs/swift/rfc/admin-ops-capabilities/PLATFORM-POSTGRES.md`.

## Registration

Installing this package *is* the registration: the fred-agents pod
auto-discovers each capability at boot via the `fred.capabilities` entry
points declared in `pyproject.toml`.
