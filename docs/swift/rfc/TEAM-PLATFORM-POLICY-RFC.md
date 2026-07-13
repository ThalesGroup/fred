# RFC — Team Platform Policy

**Status:** Draft for team review  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-23  
**Area:** `control-plane-backend`, `knowledge-flow-backend`, `frontend`  
**Related:** `FRED-TEAM-CONFIG-RFC.md`

---

## 1. Problem

Fred currently has no typed team-level object for platform-enforced guardrails.

Examples that the product needs:

- maximum file size accepted into the team object store
- maximum object-store footprint per user inside one team
- maximum source file size accepted by ingestion
- allowed model profiles for the team
- allowed MCP servers for the team

Without a dedicated object, these rules would leak into:

- ad hoc environment variables
- runtime catalogs
- generic agent tuning fields
- frontend-only assumptions

That would mix platform safety concerns with business configuration, which this
RFC explicitly forbids.

---

## 2. V1 scope

V1 intentionally stays small. It covers only the minimum team-level platform
guardrails needed to unblock future UI and routing work.

Included:

- object-store upload size cap
- object-store per-user footprint (bytes and file count)
- team-wide aggregate storage cap
- team-wide user count cap
- ingestion source-file size cap
- ingestion batch file-count cap
- allowed model profile IDs
- allowed MCP server IDs
- user deletion data retention (conversations and documents)

Not included in V1:

- billing budgets
- request rate limits
- provider-level retry or timeout tuning
- per-user model-routing policies

---

## 3. Data model

```python
class TeamPlatformPolicy(BaseModel):
    team_id: TeamId
    version: int
    storage: TeamStoragePolicy
    ingestion: TeamIngestionPolicy
    size: TeamSizePolicy
    deletion_retention: UserDeletionRetentionPolicy
    model_guardrails: TeamModelGuardrails
    tool_guardrails: TeamToolGuardrails


class TeamStoragePolicy(BaseModel):
    max_object_upload_bytes: int      # per-upload hard cap
    max_user_object_bytes_total: int  # per-user cumulative bytes cap
    max_user_file_count: int          # per-user cumulative file count cap
    team_storage_bytes_total: int     # team-wide aggregate bytes cap


class TeamSizePolicy(BaseModel):
    max_users: int                    # maximum number of members in this team


class UserDeletionRetentionPolicy(BaseModel):
    conversations_retention_days: int  # 0 = immediate purge on user deletion
    documents_retention_days: int      # 0 = immediate purge on user deletion


class TeamIngestionPolicy(BaseModel):
    max_source_file_bytes: int
    max_batch_file_count: int


class TeamModelGuardrails(BaseModel):
    allowed_profile_ids: list[str] | None = None


class TeamToolGuardrails(BaseModel):
    allowed_mcp_server_ids: list[str] | None = None
```

### 3.1 Field semantics

`storage.max_object_upload_bytes`

- hard limit for one object upload into the team object store
- enforced before the object is persisted

`storage.max_user_object_bytes_total`

- hard limit for the sum of object-store bytes owned by one user in this team
- evaluated as current total plus incoming upload size

`storage.max_user_file_count`

- hard limit for the number of files owned by one user in this team
- evaluated as current count plus number of files in the incoming upload

`storage.team_storage_bytes_total`

- hard limit for the total bytes stored across all users in this team
- the team-wide ceiling that bounds what per-user quotas can collectively reach
- enforced before persisting any new object

`size.max_users`

- hard limit on how many members (including the team admin) the team may have
- enforced at team member add time; adding a member to a full team is rejected

`deletion_retention.conversations_retention_days`

- how many days a deleted user's conversation history is retained before purge
- `0` means purge immediately when the delete-user task reaches that step
- used by the delete-user activity to schedule `PurgeQueueStore` entries

`deletion_retention.documents_retention_days`

- how many days a deleted user's personal documents are retained before purge
- `0` means immediate deletion of the user's objects from the object store
- used by the delete-user activity the same way as conversations above

`ingestion.max_source_file_bytes`

- hard limit for one source file accepted by ingestion
- enforced before the file enters ingestion work

`ingestion.max_batch_file_count`

- hard limit for one ingestion request containing multiple files

`model_guardrails.allowed_profile_ids`

- `null` means "no team-specific narrowing; use deployment defaults"
- non-empty list means "team routing and agent configuration may only reference
  these profile IDs"

`tool_guardrails.allowed_mcp_server_ids`

- `null` means "no team-specific narrowing; use deployment defaults"
- non-empty list means "team-managed agents may only activate these MCP server
  IDs"

### 3.2 Invariants

All of the following are required:

- numeric values are positive integers
- `max_batch_file_count >= 1`
- `max_users >= 1`
- `conversations_retention_days >= 0`, `documents_retention_days >= 0`
- allowlist entries are unique, non-empty strings
- if deployment-level ceilings exist, team values must be less than or equal to
  those ceilings
- `team_storage_bytes_total >= max_user_object_bytes_total` (the aggregate cap
  must be at least as large as one user's per-user cap)
- empty allowlists are rejected in V1 to avoid accidental team-wide lockout

---

## 4. Example

```yaml
team_id: bid-and-capture
version: 3
storage:
  max_object_upload_bytes: 52428800       # 50 MB per upload
  max_user_object_bytes_total: 5368709120  # 5 GB per user
  max_user_file_count: 1000               # 1 000 files per user
  team_storage_bytes_total: 53687091200   # 50 GB team aggregate
ingestion:
  max_source_file_bytes: 104857600        # 100 MB per source file
  max_batch_file_count: 20
size:
  max_users: 50
deletion_retention:
  conversations_retention_days: 7
  documents_retention_days: 1
model_guardrails:
  allowed_profile_ids:
    - default.chat.mistral
    - chat.openai.gpt5mini
    - chat.openai.gpt5
tool_guardrails:
  allowed_mcp_server_ids:
    - mcp-knowledge-flow-mcp-text
    - mcp-knowledge-flow-corpus
```

This means:

- one uploaded object cannot exceed 50 MB
- one user cannot exceed 5 GB and 1 000 files of stored objects in that team
- the entire team cannot exceed 50 GB of stored objects across all users
- the team cannot grow beyond 50 members
- when a user is deleted, their conversations are purged after 7 days and their
  documents after 1 day
- one ingestion source file cannot exceed 100 MB
- one ingestion request cannot contain more than 20 files
- routing policy and managed-agent configuration can only reference the listed
  model profiles and MCP servers

---

## 5. Authorization

Read:

- team_admin
- team_editor

Write:

- team_admin only

Business rule:

- platform policy is `team_admin`-owned because it defines team safety guardrails
- `team_editor`s may inspect those guardrails but may not relax them

(Terminology note: this RFC predates the AUTHZ-05 team-role rename —
`owner`/`manager`/`member` are now `team_admin`/`team_editor`/`team_member`,
RFC `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` §26. Updated here for consistency,
2026-07-10.)

---

## 6. Enforcement points

Platform policy is not documentation-only. Each field has a required owner
service.

| Policy field                             | Enforcement point                                                          |
| ---------------------------------------- | -------------------------------------------------------------------------- |
| `storage.max_object_upload_bytes`        | object upload boundary in Knowledge Flow / team-scoped filesystem surfaces |
| `storage.max_user_object_bytes_total`    | object-store write path before persist                                     |
| `storage.max_user_file_count`            | object-store write path before persist                                     |
| `storage.team_storage_bytes_total`       | object-store write path before persist (after per-user check)              |
| `size.max_users`                         | team member add endpoint before inserting the new membership relation      |
| `deletion_retention.*`                   | delete-user activity: drives `PurgeQueueStore` scheduling at task time     |
| `ingestion.max_source_file_bytes`        | ingestion upload boundary before temp-file persistence                     |
| `ingestion.max_batch_file_count`         | ingestion controller request validation                                    |
| `model_guardrails.allowed_profile_ids`   | team routing policy writes and future managed-agent model selection writes |
| `tool_guardrails.allowed_mcp_server_ids` | managed-agent create/update and runtime preparation validation             |

### 6.1 Rejection behavior

All enforcement must fail closed with explicit product errors.

Required behavior:

- no silent truncation
- no implicit fallback to a smaller model
- no automatic removal of disallowed MCP servers

If a request violates policy, the backend returns an explicit 4xx error naming
the violated field.

---

## 7. Interaction with existing and future surfaces

### 7.1 Team routing policy

Every profile referenced by `TeamRoutingPolicy` must belong to
`model_guardrails.allowed_profile_ids` when that allowlist is non-null.

### 7.2 Managed-agent configuration

If a future per-instance model selector exists, it must also be bounded by
`allowed_profile_ids`.

Every selected MCP server ID must belong to `allowed_mcp_server_ids` when that
allowlist is non-null.

### 7.3 Prompt library

Prompt authoring is not directly constrained by platform policy in V1.

Prompt usage may still be indirectly constrained because:

- prompt-backed agents run under routing policy
- prompt-backed agents may activate only allowed MCP servers

---

## 8. API contract

Future API surface:

```text
GET   /control-plane/v1/teams/{team_id}/platform-policy
PATCH /control-plane/v1/teams/{team_id}/platform-policy
```

Rules:

- `GET` returns the stored policy or the resolved default team policy if no team
  override exists yet
- `PATCH` is a full replacement of the typed policy body in V1
- policy creation is implicit on first successful `PATCH`

V1 intentionally avoids per-field patch semantics.

---

## 9. Update safety rule

A policy update must be rejected if it would immediately invalidate already
stored team configuration without an explicit remediation path.

At minimum, the control-plane must reject a new platform policy when:

- the current team routing policy references a profile that the new allowlist
  would forbid
- existing managed agents reference MCP servers that the new allowlist would
  forbid

This avoids turning policy writes into hidden breakage.

---

## 10. Storage authority

`TeamPlatformPolicy` is a control-plane product object.

It must be stored in control-plane persistence, not in:

- runtime pod YAML
- frontend local state
- Knowledge Flow-only configuration

Deployment defaults may still come from configuration files, but team overrides
belong in control-plane storage.

---

## 11. Non-goals for implementation

When this RFC is implemented, V1 still does not need:

- background quota rebalancing
- cost budgeting by provider
- historical policy version browser UI
- policy inheritance trees across sub-teams

V1 only needs a strict, explicit, team-level guardrail object.

---

## 12. Configuration-driven defaults

All `TeamPlatformPolicy` field defaults come from the deployment configuration
file (`configuration.yaml`), not from Pydantic model defaults. This allows
on-premise operators to tune the baseline for their environment without code
changes.

### 12.1 Configuration shape

```yaml
# configuration.yaml
team_policy_defaults:
  regular:
    storage:
      max_object_upload_bytes: 52428800         # 50 MB
      max_user_object_bytes_total: 5368709120   # 5 GB
      max_user_file_count: 1000
      team_storage_bytes_total: 107374182400    # 100 GB
    ingestion:
      max_source_file_bytes: 104857600          # 100 MB
      max_batch_file_count: 20
    size:
      max_users: 50
    deletion_retention:
      conversations_retention_days: 7
      documents_retention_days: 1

  personal:
    storage:
      max_object_upload_bytes: 10485760         # 10 MB
      max_user_object_bytes_total: 1073741824   # 1 GB
      max_user_file_count: 200
      team_storage_bytes_total: 1073741824      # same as per-user (single owner)
    ingestion:
      max_source_file_bytes: 52428800           # 50 MB
      max_batch_file_count: 5
    size:
      max_users: 1                              # personal team is always single-user
    deletion_retention:
      conversations_retention_days: 0           # immediate: personal data purged on account deletion
      documents_retention_days: 0
```

### 12.2 Resolution rule

When control-plane reads a team's platform policy:

1. Load the deployment default matching the team type (`regular` or `personal`).
2. If a team-specific override row exists in `team_platform_policy` storage,
   merge it over the default (full replacement, not field-level merge).
3. Return the resolved policy.

`GET /teams/{team_id}/platform-policy` always returns the resolved policy, not
just the override delta. This keeps the API contract simple for callers.

### 12.3 Personal team defaults

Personal teams (`personal-{uid}`) always resolve from the `personal` default
block, not the `regular` block. Key differences:

- `size.max_users` is hardcoded to `1` and cannot be overridden, even by a
  platform admin write. The API rejects any PATCH that sets `max_users != 1`
  on a personal team.
- `deletion_retention` defaults to `0` for both fields: when a user deletes
  their account, their personal data is purged immediately unless a platform
  admin has explicitly set longer retention (e.g. for compliance/legal hold).
- The personal team policy is created automatically when a personal team is
  created; no manual PATCH is required for defaults to apply.

---

## 13. Team creation and initial policy assignment

**Updated 2026-07-10 for consistency with the shipped implementation** (RFC
`FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` §28, revised by Part 6 §29-32 /
AUTHZ-05 review item 9). Team creation already exists and works differently
from the original draft below: there is no Keycloak group — a team is a
`team_metadata` row plus OpenFGA relations, full stop.

```
POST /control-plane/v1/teams
Auth: platform_admin (can_create_team)
Body: {
  name: str,
  initial_team_admin_ids: list[str]   // Keycloak user sub(s) — min 1
}
→ 201 TeamWithPermissions
→ 409 if a team with this name already exists
```

Team creation atomically:

1. Checks name uniqueness against `team_metadata_store`.
2. Generates a fresh `uuid4().hex` team id and creates the `team_metadata` row.
3. Writes `team_admin` OpenFGA relations for each `initial_team_admin_ids`
   entry. On failure, rolls back the `team_metadata` row (one-shot by
   construction — no Keycloak group to roll back).

**Not yet implemented** (this RFC's own scope, tracked separately in
`BACKLOG.md` §TEAM-03, blocked on `TeamPlatformPolicy` shipping first): step 3
above — writing the initial `team_platform_policy` row from the request body
or the `regular` default. The endpoint contract shown above does not yet
accept a `platform_policy` field; when it's added, follow the same
one-shot/rollback shape as the two steps above, not a Keycloak-era three-way
best-effort cleanup (there is no external system in the loop anymore).

### 13.1 What the team settings page exposes

The team settings page has two panels, driven by the caller's role. (Renamed
for consistency, 2026-07-10 — the original draft's "Platform admin view
(owner)" label was ambiguous with the unrelated org-level `platform_admin`
role; both panels below are team-scoped views, gated on `team_admin`/
`team_editor` respectively, per REBAC.md's "hard cross-write rule.")

**`team_admin` view:**

| Panel | Contents | Editable |
|---|---|---|
| Platform limits | Full `TeamPlatformPolicy` — all fields | Yes (`PATCH /platform-policy`) |
| Routing policy | `TeamRoutingPolicy` | No (`team_editor`-owned) |

**`team_editor` view:**

| Panel | Contents | Editable |
|---|---|---|
| Platform limits | Full `TeamPlatformPolicy` — all fields | No (read-only) |
| Routing policy | `TeamRoutingPolicy` | Yes (`PATCH /routing-policy`) |

The read-only platform panel shows the resolved policy (defaults merged with
overrides), not the raw override delta. No "inherited from defaults" annotation
is needed in V1 — the full resolved values are enough.

### 13.2 Keycloak requirement

**Removed 2026-07-10 (no longer applies).** Team creation and membership no
longer call Keycloak at all — no M2M client role is required. Keycloak is
identity-only (login, JWT, stable `sub`); teams are `team_metadata` rows plus
OpenFGA relations (AUTHZ-05 review item 9).
