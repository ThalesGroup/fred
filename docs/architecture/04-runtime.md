# 4. Runtime

## fred-manager HTTP surface

Every route but the health probe requires a bearer token (chapter 6).

<!-- generated: routes apps/fred-manager/src/api.rs /fred-manager/v1 -->
| Method | Path | Handler |
| --- | --- | --- |
| GET | `/fred-manager/v1/healthz` | `inline` |
| POST | `/fred-manager/v1/bootstrap/platform-admin` | `bootstrap_platform_admin` |
| GET | `/fred-manager/v1/me` | `me` |
| GET | `/fred-manager/v1/me/spaces` | `my_spaces` |
| POST | `/fred-manager/v1/me/personal-space` | `create_personal_space` |
| POST | `/fred-manager/v1/spaces` | `create_space` |
| PUT | `/fred-manager/v1/spaces/{id}/roles/{role}/{user}` | `grant` |
| DELETE | `/fred-manager/v1/spaces/{id}/roles/{role}/{user}` | `revoke` |
| GET | `/fred-manager/v1/spaces/{id}/folders` | `list_folders` |
| GET | `/fred-manager/v1/spaces/{id}/documents` | `list_documents` |
| POST | `/fred-manager/v1/folders` | `create_folder` |
| PATCH | `/fred-manager/v1/folders/{id}` | `rename_folder` |
| DELETE | `/fred-manager/v1/folders/{id}` | `delete_folder` |
| POST | `/fred-manager/v1/documents` | `create_document` |
| GET | `/fred-manager/v1/documents/{id}` | `get_document` |
| PATCH | `/fred-manager/v1/documents/{id}` | `rename_document` |
| DELETE | `/fred-manager/v1/documents/{id}` | `delete_document` |
| POST | `/fred-manager/v1/documents/{id}/ingest` | `ingest_document` |
| POST | `/fred-manager/v1/authorize/document` | `authorize_document` |
| POST | `/fred-manager/v1/authorize/scope` | `authorize_scope` |
<!-- end generated -->

## Content access

One OpenFGA check on the space that owns the content, whatever the content is: a
document, its metadata, a page of a folder.

```mermaid
sequenceDiagram
    participant UI
    participant M as fred-manager
    participant KC as Keycloak
    participant PG as Postgres
    participant FGA as OpenFGA
    UI->>M: GET /documents/{id}, Bearer token
    Note over M: request span: request_id, correlation_id
    opt unknown kid, at most once per 30 s
        M->>KC: GET realm certs
    end
    Note over M: RS256, exp, iat, lifetime ceiling, then user_id bound
    M->>PG: select document
    M->>FGA: check user can_read space:{document.space_id}
    alt allowed
        M-->>UI: 200 document
    else denied
        M-->>UI: 403
    end
    Note over M: one completion event on logger http
```

## Agent search scope

The agent calls with the user's own token. The scope is the space and its ancestors,
never its descendants (I7): a team conversation never sees its projects' content.

```mermaid
sequenceDiagram
    participant A as fred-agents
    participant M as fred-manager
    participant FGA as OpenFGA
    participant OS as OpenSearch
    A->>M: POST /authorize/scope {space_id}, user's token
    M->>FGA: check user can_read space:{space_id}
    M-->>A: {space_ids: path of the space}
    A->>OS: query, filter space_id in space_ids,<br/>optionally folder_path prefix
```

## Role and space mutations

`grant`, `revoke`, `create_space` and `create_personal_space` take a transaction-scoped
advisory lock keyed by the organization, then check and write under it (I4, I5).

```mermaid
sequenceDiagram
    participant C as Caller
    participant M as fred-manager
    participant PG as Postgres
    participant FGA as OpenFGA
    C->>M: PUT /spaces/{id}/roles/{role}/{user}
    M->>PG: select space
    M->>PG: begin, pg_advisory_xact_lock(organization)
    M->>FGA: check caller can_manage space
    M->>FGA: check target can_read parent
    M->>FGA: write tuple, on_duplicate ignore
    M->>PG: commit, lock released
    M-->>C: 204
```

Revocation also reads the target's roles and the space's children under the lock, and
refuses with 409 when the target would keep a role in a child without reading its
parent. A personal space is managed from its organization: an organization admin may
revoke its owner's roles, nobody may grant any (I6).

## Root platform-admin bootstrap

Two proofs: the caller's verified bearer and the deploy-time secret
(`app.bootstrap_token_env_var`, compared in constant time). Two transactions under one
advisory lock (I9).

```mermaid
sequenceDiagram
    participant U as Caller
    participant M as fred-manager
    participant PG as Postgres
    participant FGA as OpenFGA
    U->>M: POST /bootstrap/platform-admin {token}
    Note over M: 422 short token, 403 wrong secret, 503 authentication disabled
    M->>PG: lock, read marker
    alt no marker
        M->>PG: insert completed_by = caller, commit
    else pending for another caller, or granted
        M-->>U: 409
    end
    M->>PG: lock again, re-read marker
    alt still pending for this caller
        M->>FGA: write admin on platform:root
        M->>PG: set granted_at, commit
        M-->>U: 200
    else granted meanwhile
        M-->>U: 409
    end
```

```mermaid
stateDiagram-v2
    [*] --> Unclaimed
    Unclaimed --> Pending: first caller reserves
    Pending --> Pending: same caller retries after a failure
    Pending --> Granted: tuple written, granted_at set
    Granted --> Granted: every later call gets 409
```

## Ingestion submission

`POST /documents` registers a document and returns its `storage_prefix`
(`<space_id>/<document_id>/`) and `source_key` (`<prefix>source`). Uploading the source
is not built yet. Workflow ids are `ingest-<document_id>` and `delete-<document_id>`:
a second ingestion while one runs answers 409.

```mermaid
sequenceDiagram
    participant UI
    participant M as fred-manager
    participant T as Temporal
    participant W as worker
    UI->>M: POST /documents/{id}/ingest {profile}
    M->>M: check can_write on the document's space
    M->>T: start IngestDocument, id ingest-{id}, queue fred-ingestion
    M-->>UI: 202, or 409 when already running
    T->>W: IngestDocument {document_id, space_id, folder_path,<br/>storage_prefix, source_key, mime, profile, requested_by}
    Note over W: not implemented yet
```

Deletion submits `DeleteDocument {document_id, space_id, storage_prefix}` before
deleting the row, so a failure leaves a retryable document rather than orphaned chunks.
