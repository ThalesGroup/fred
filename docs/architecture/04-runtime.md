# 4. Runtime

## fred-manager HTTP surface

Every route but the health probe requires a bearer token (chapter 6).

<!-- generated: routes apps/fred-manager/src/api.rs /fred-manager/v1 -->
| Method | Path | Handler |
| --- | --- | --- |
| GET | `/fred-manager/v1/healthz` | `inline` |
| POST | `/fred-manager/v1/bootstrap/platform-admin` | `bootstrap_platform_admin` |
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
| GET | `/fred-manager/v1/me` | `me` |
| GET | `/fred-manager/v1/users/platform-roles` | `list_platform_roles` |
| PUT | `/fred-manager/v1/users/{user}/platform-roles/{role}` | `grant_platform_role` |
| DELETE | `/fred-manager/v1/users/{user}/platform-roles/{role}` | `revoke_platform_role` |
| GET | `/fred-manager/v1/admin/teams` | `team_registry` |
| POST | `/fred-manager/v1/authorize/platform` | `authorize_platform` |
| POST | `/fred-manager/v1/authorize/space` | `authorize_space` |
<!-- end generated -->

## Content access

One OpenFGA check on the space that owns the content, whatever the content is: a
document, its metadata, a page of a folder.

```mermaid
sequenceDiagram
    participant C as Client
    participant M as fred-manager
    participant KC as Keycloak
    participant PG as Postgres
    participant FGA as OpenFGA
    C->>M: GET /documents/{id}, Bearer token
    Note over M: request span: request_id, correlation_id
    opt unknown kid, at most once per 30 s
        M->>KC: GET realm certs
    end
    Note over M: RS256, exp, iat, lifetime ceiling, then user_id bound
    M->>PG: select document
    M->>FGA: check user can_read space:{document.space_id}
    alt allowed
        M-->>C: 200 document
    else denied
        M-->>C: 403
    end
    Note over M: one completion event on logger http
```

## Search scope

A service acting for a user calls with that user's own token. The scope is the space
and its ancestors, never its descendants (I7): from a team, a project's content is out
of scope. The caller filters indexed content with `space_id` in the returned ids, and
narrows to a folder with a `folder_path` prefix.

```mermaid
sequenceDiagram
    participant S as Service acting for a user
    participant M as fred-manager
    participant PG as Postgres
    participant FGA as OpenFGA
    S->>M: POST /authorize/scope {space_id}, user's token
    M->>PG: select space
    M->>FGA: check user can_read space:{space_id}
    M-->>S: {space_ids: path of the space}
```

## Role and space mutations

`grant`, `revoke`, `create_space` and `create_personal_space` take a transaction-scoped
advisory lock keyed by the organization, capture its guard revision, then check and
write under it (I4, I5). SQL locks order live callers; OpenFGA guard consumption
rejects stale remote writes that outlive their caller or transaction.

```mermaid
sequenceDiagram
    participant C as Caller
    participant M as fred-manager
    participant PG as Postgres
    participant FGA as OpenFGA
    C->>M: PUT /spaces/{id}/roles/{role}/{user}
    M->>PG: select space
    M->>PG: begin, pg_advisory_xact_lock(organization)
    M->>FGA: read organization guard revision
    M->>FGA: check caller can_manage space
    M->>FGA: check target can_read parent
    M->>FGA: atomic role write and guard replacement, strict old-guard delete
    M->>PG: commit, lock released
    M-->>C: 204
```

Revocation also reads the target's roles and the space's children under the lock, and
refuses with 409 when the target would keep a role in a child without reading its
parent. Removing the last administrator of a non-personal space is refused with 409 (I14).
Removing a role never grants a replacement content role. A personal space is managed from its organization: an organization admin may
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
(`<space_id>/<document_id>/`) and `source_key` (`<prefix>source`). Workflow ids are
`ingest-<document_id>` and `delete-<document_id>`: a second ingestion while one runs
answers 409.

```mermaid
sequenceDiagram
    participant C as Client
    participant M as fred-manager
    participant FGA as OpenFGA
    participant T as Temporal
    C->>M: POST /documents/{id}/ingest {profile}
    M->>FGA: check user can_write on the document's space
    M->>T: start IngestDocument, id ingest-{id}, queue fred-ingestion
    M-->>C: 202, or 409 when already running
```

| Workflow | Input |
| --- | --- |
| `IngestDocument` | `document_id`, `space_id`, `folder_path`, `storage_prefix`, `source_key`, `mime`, `profile` (default `medium`), `requested_by` |
| `DeleteDocument` | `document_id`, `space_id`, `storage_prefix` |

Deletion submits `DeleteDocument {document_id, space_id, storage_prefix}` before
deleting the row, so a failure leaves a retryable document rather than orphaned chunks.

## Platform administration and self checks

`GET /me` returns effective platform roles, including the roles implied by platform
admin. `GET /users/platform-roles` returns direct grants only, to platform admins.
`PUT` and `DELETE /users/{user}/platform-roles/{role}` acquire the bootstrap/platform
lock and recheck the caller's platform-admin permission. Only the completed bootstrap
root can grant or revoke platform admin, and its own admin grant cannot be removed.
Granting requires a Keycloak subject that exists in the configured directory; revoking
a stale direct grant does not require the identity to still exist (I15).

Platform roles use canonical names `platform_admin`, `platform_observer`, `team_manager`,
`feature_manager` and `prompt_editor`; mutation paths also accept `admin` and `observer`.
Deleting an absent direct grant returns 404, even when the role is effective through admin.

`POST /authorize/platform` accepts `{ "permission": "create_team" }`;
`POST /authorize/space` accepts `{ "space_id": "<uuid>", "permission": "run_evaluations" }`.
Both return `{ "allowed": true|false }` for the authenticated caller only. The typed
capabilities are defined in `roles.rs` and the model in chapter 5. Space checks first
resolve the space, returning 404 for an unknown id.

`GET /admin/teams` requires `can_list_all_teams` and returns at most 100 non-personal
team metadata records ordered by UUID. `?after=<uuid>` continues after the last id;
it confers no content access.

Team creation accepts either management of the parent organization or the platform
`can_create_team` capability. It takes the platform lock before the organization lock,
then checks authorization. The nominated team administrator must read the parent.
The caller receives no implicit role; project creation still requires local governance.

## Authenticated provisioning import

`fred-manager import-provisioning <bundle.json> --token-file <path>` verifies the
operator bearer, connects to SQL without migrating and verifies migration
versions/checksums. It loads the published FGA store/model and checks platform admin. A bundle
that declares platform admin additionally requires the completed bootstrap root.

```mermaid
sequenceDiagram
    participant C as CLI
    participant KC as Keycloak
    participant PG as Postgres
    participant FGA as OpenFGA
    C->>KC: verify operator bearer using signing keys
    C->>PG: verify schema, read published store/model binding
    C->>FGA: verify pinned model, check platform admin
    C->>PG: lock platform then existing organization
    C->>FGA: recheck authority and root-only declarations
    C->>PG: validate space names, release read-only locks
    C->>KC: preflight every exact username and missing password
    loop each identity
        C->>PG: lock platform
        C->>FGA: read platform guard, recheck authority, consume guard
        C->>KC: resolve or create with service credentials
        C->>PG: release lock
    end
    C->>PG: lock platform then organization, reread space names
    C->>FGA: initialize new organization guard, capture both guards
    C->>PG: insert missing organization row
    C->>FGA: recheck bearer/authority, guarded parent grants
    C->>PG: insert missing team rows
    C->>FGA: guarded team/platform grants, audit acknowledgments
    C->>PG: commit space rows, release locks
```

All predictable bundle, passwordless-identity and new-team-admin errors fail preflight
before provisioning writes (I18). Read-only directory traversal holds no mutation lock.
Each identity phase holds the platform lock; reconciliation holds platform then organization
locks through its writes. Bearer verification and FGA authority checks repeat at mutation
boundaries, including after lock waits. Space grants use batches of at most 96 role tuples plus four guard operations,
with organization membership before dependent child roles (I4, I5).

Organizations are resolved by root name, teams by organization and name. Existing IDs
are reused; incompatible or personal-space name collisions are refused. Existing users
are resolved by exact username without updating their profile/password. Lookup is paginated
and rejects ambiguous or inexact replies; a creation conflict triggers a fresh lookup.

Reconciliation is additive (I17). Undeclared roles remain; missing declared grants are
repaired. A renamed declaration identifies a different space. There is no distributed
rollback: identities and acknowledged FGA grants can survive a failed SQL transaction.
New space rows commit after their initial grants; rolled-back UUIDs are never reused.
Replay uses committed identities/spaces and repairs the requested state.

Local folder/document mutations capture the organization guard, authorize, consume
the guard and commit SQL under the same organization lock. Placement reads use the
held SQL connection. Temporal submission holds that lock through dispatch; its
remote effects have the dispatch boundary described by I5 in chapter 5.
