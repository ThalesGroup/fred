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
- object-store per-user footprint cap
- ingestion source-file size cap
- ingestion batch file-count cap
- allowed model profile IDs
- allowed MCP server IDs

Not included in V1:

- billing budgets
- request rate limits
- provider-level retry or timeout tuning
- per-user model-routing policies
- per-team storage lifecycle rules

---

## 3. Data model

```python
class TeamPlatformPolicy(BaseModel):
    team_id: TeamId
    version: int
    storage: TeamStoragePolicy
    ingestion: TeamIngestionPolicy
    model_guardrails: TeamModelGuardrails
    tool_guardrails: TeamToolGuardrails


class TeamStoragePolicy(BaseModel):
    max_object_upload_bytes: int
    max_user_object_bytes_total: int


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
- evaluated as current total plus incoming upload

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
- allowlist entries are unique, non-empty strings
- if deployment-level ceilings exist, team values must be less than or equal to
  those ceilings
- empty allowlists are rejected in V1 to avoid accidental team-wide lockout

---

## 4. Example

```yaml
team_id: bid-and-capture
version: 3
storage:
  max_object_upload_bytes: 52428800
  max_user_object_bytes_total: 2147483648
ingestion:
  max_source_file_bytes: 104857600
  max_batch_file_count: 20
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
- one user cannot exceed 2 GB of stored objects in that team
- one ingestion source file cannot exceed 100 MB
- one ingestion request cannot contain more than 20 files
- routing policy and managed-agent configuration can only reference the listed
  model profiles and MCP servers

---

## 5. Authorization

Read:

- team owner
- team manager

Write:

- team owner only

Business rule:

- platform policy is owner-owned because it defines team safety guardrails
- managers may inspect those guardrails but may not relax them

---

## 6. Enforcement points

Platform policy is not documentation-only. Each field has a required owner
service.

| Policy field | Enforcement point |
|---|---|
| `storage.max_object_upload_bytes` | object upload boundary in Knowledge Flow / team-scoped filesystem surfaces |
| `storage.max_user_object_bytes_total` | object-store write path before persist |
| `ingestion.max_source_file_bytes` | ingestion upload boundary before temp-file persistence |
| `ingestion.max_batch_file_count` | ingestion controller request validation |
| `model_guardrails.allowed_profile_ids` | team routing policy writes and future managed-agent model selection writes |
| `tool_guardrails.allowed_mcp_server_ids` | managed-agent create/update and runtime preparation validation |

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
