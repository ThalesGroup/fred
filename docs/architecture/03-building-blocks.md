# 3. Building blocks

## fred-manager

A library crate (`src/lib.rs`) with a thin binary (`src/main.rs`): integration tests
drive the library against real Postgres and OpenFGA.

```mermaid
flowchart TB
    main["main.rs<br/>serve, create-org, import-provisioning"]
    config["config.rs<br/>configuration.yaml + secrets"]
    logging["logging.rs<br/>stdout format, request ids"]
    api["api.rs<br/>routes, handlers"]
    auth["auth.rs<br/>bearer verification"]
    error["error.rs<br/>error contract"]
    spaces["spaces.rs<br/>space and role mutations"]
    provisioning["provisioning.rs<br/>bundle validation and reconciliation"]
    platform["platform.rs<br/>platform-role administration"]
    roles["roles.rs<br/>roles and capabilities"]
    directory["keycloak.rs<br/>service-account directory"]
    bootstrap["bootstrap.rs<br/>root platform admin"]
    domain["domain.rs<br/>types, placement rules"]
    db["db.rs<br/>SQL"]
    fga["fga.rs<br/>OpenFGA client"]
    ingestion["ingestion.rs<br/>Temporal client"]

    main --> config & logging & api & provisioning
    provisioning --> auth & platform & directory & db & fga & spaces
    api --> auth & error & spaces & bootstrap & db & fga & ingestion & logging
    spaces --> domain & db & fga
    api --> platform & roles & directory
    platform --> bootstrap & directory & fga
    fga --> roles
    bootstrap --> fga
    db --> domain
    fga --> domain
```

| Module | Owns | Rule it enforces |
| --- | --- | --- |
| `api` | HTTP surface, one OpenFGA check per content access | handlers stay thin; mutations live in `spaces` and `platform` |
| `auth` | `CurrentUser` extractor, JWKS cache | chapter 6 |
| `spaces` | create space, grant, revoke | check and write under the organization lock (I4, I5) |
| `bootstrap` | the one-time root grant | two steps under the bootstrap lock (I9) |
| `domain` | `Space`, `Folder`, `Document`, roles, parent rules | pure functions, unit-tested (I1, I7) |
| `db` | content and space SQL | placement columns written by inserts only (I2) |
| `fga` | store discovery, model sync, check, write, read | idempotent writes |
| `ingestion` | `IngestDocument`, `DeleteDocument` submission | one workflow id per document and operation |
| `logging` | output format, request span, completion event | chapter 6 (I11, I13) |
| `error` | status codes, `{"detail": ...}` bodies | chapter 6 |

`roles` defines typed platform roles and scoped capabilities. `platform` serializes
role mutations with bootstrap. `keycloak` owns one shared HTTP client and a synchronized
service-token cache. `api::governance_router` groups identity, platform administration
and self-capability routes independently of the Temporal client.

`provisioning::Bundle` validates and normalizes declarations without exposing credentials
through Debug or serialization. `Importer` performs read-only preflight, per-identity
mutations, then additive space/role reconciliation. The binary connects without SQL
migration or FGA model synchronization, and does not initialize Temporal for import.
