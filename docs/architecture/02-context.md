# 2. Context

```mermaid
flowchart LR
    client["Client<br/>browser application"]
    caller["Service acting for a user<br/>with the user's token"]
    manager["fred-manager<br/>REST API /fred-manager/v1"]
    keycloak["Keycloak<br/>realm app"]
    openfga["OpenFGA<br/>store fred-manager"]
    postgres[("Postgres<br/>database fred")]
    temporal["Temporal<br/>queue fred-ingestion"]

    client -- "bearer token" --> manager
    caller -- "authorize document,<br/>authorize scope" --> manager
    client -- "login" --> keycloak
    manager -- "signing keys" --> keycloak
    manager -- "one check per access,<br/>role writes" --> openfga
    manager -- "spaces, folders, documents" --> postgres
    manager -- "IngestDocument,<br/>DeleteDocument" --> temporal
```

| Partner | What fred-manager uses | Contract |
| --- | --- | --- |
| Keycloak | Access tokens, signing keys (JWKS) | chapter 6, Authentication |
| OpenFGA | `check`, `write`, `read` on its own store | chapter 5, OpenFGA model |
| Postgres | Its tables in the `fred` database | chapter 5, Schema |
| Temporal | Starting `IngestDocument` and `DeleteDocument` | chapter 4, Ingestion submission |
| Clients | Every route; the health probe needs no token | chapters 4 and 6 |
| Services acting for a user | `/authorize/document`, `/authorize/scope` | chapter 4, Search scope |
