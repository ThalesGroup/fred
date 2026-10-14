# 2. Context

```mermaid
flowchart LR
    ui["Fred UI<br/>browser"]
    agents["fred-agents<br/>Python"]
    subgraph manager_box [fred-manager, Rust]
        manager["REST API<br/>/fred-manager/v1"]
    end
    keycloak["Keycloak realm app<br/>OIDC, JWKS"]
    openfga["OpenFGA<br/>store fred-manager"]
    postgres[("Postgres<br/>database fred")]
    temporal["Temporal<br/>queue fred-ingestion"]
    worker["knowledge-flow worker<br/>Python, not yet adapted"]
    storage[("Object storage<br/>space/document/...")]
    index[("OpenSearch<br/>chunks")]

    ui -- "bearer token" --> manager
    agents -- "authorize document / scope,<br/>with the user's token" --> manager
    ui -- "login" --> keycloak
    manager -- "signing keys" --> keycloak
    manager -- "one check per access,<br/>role writes" --> openfga
    manager -- "spaces, folders, documents" --> postgres
    manager -- "IngestDocument,<br/>DeleteDocument" --> temporal
    temporal --> worker
    worker --> storage
    worker --> index
```

| Partner | What fred-manager needs from it | Contract |
| --- | --- | --- |
| Keycloak | Access tokens, signing keys | chapter 6, Authentication |
| OpenFGA | `check`, `write`, `read` on its own store | chapter 5, OpenFGA model |
| Postgres | Its tables in the shared `fred` database | chapter 5, Schema |
| Temporal | Starting two workflows | chapter 4, Ingestion submission |
| fred-agents | Calls `/authorize/*` with the user's token, then filters search | chapter 4, Agent search scope |
| UI | Every route except the health probe | chapter 6, Errors |

Today the UI still talks to the control-plane and knowledge-flow backends; how it moves
to `fred-manager` is open (chapter 10).
