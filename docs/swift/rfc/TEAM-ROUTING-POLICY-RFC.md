# RFC — Team Routing Policy

**Status:** Draft for team review  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-23  
**Area:** `control-plane-backend`, `fred-runtime`, `frontend`  
**Related:** `FRED-TEAM-CONFIG-RFC.md`, `TEAM-PLATFORM-POLICY-RFC.md`,
`docs/swift/platform/LLM_ROUTING_FRED.md`

---

## 1. Problem

Fred runtime already supports policy-based model routing by team and operation,
but the product layer does not yet expose a team-owned routing contract.

The target product behavior is simple:

- a team can define one default model profile for managed execution
- a team can override that default for specific operations such as `planning`
- those overrides must remain bounded by platform guardrails

Without a dedicated team routing object, model selection risks being spread
across:

- pod-local YAML only
- per-agent tuning fields
- frontend assumptions
- undocumented conventions

This RFC defines the first product version of team routing policy.

---

## 2. V1 design choice

V1 is intentionally narrower than runtime capability.

Runtime can theoretically route by:

- team
- user
- purpose
- operation
- agent

Product V1 exposes only:

- one team default chat profile
- zero or more operation rules
- optional purpose refinement on those operation rules

V1 does not expose per-user or per-agent routing.

This is enough to cover the primary use cases:

- "all agents in this team use model X"
- "all planning phases in this team use model Y"

---

## 3. Data model

```python
class TeamRoutingPolicy(BaseModel):
    team_id: TeamId
    version: int
    chat_default_profile_id: str | None = None
    operation_rules: list[TeamOperationRouteRule] = []


class TeamOperationRouteRule(BaseModel):
    rule_id: str
    operation: str
    purpose: str | None = None
    target_profile_id: str
```

### 3.1 Field semantics

`chat_default_profile_id`

- default chat profile for managed execution in this team
- `null` means "use the deployment default from the runtime catalog"

`operation`

- non-empty string emitted by runtime phases
- examples: `routing`, `planning`, `analysis`, `generate_draft`, `self_check`

`purpose`

- optional refinement of an operation rule
- example: one team may use one planning profile for all chat agents, but a
  stronger planning profile only when `purpose == "gap_analysis"`

`target_profile_id`

- stable deployment-global model profile identifier
- must exist in runtime catalogs used by the team's managed agents

### 3.2 Invariants

All of the following are required:

- `rule_id` is unique inside one team policy
- `(operation, purpose)` is unique inside one team policy
- all profile IDs are non-empty strings
- all profile IDs must be allowed by `TeamPlatformPolicy.model_guardrails` when
  that allowlist is set

---

## 4. Resolution algorithm

V1 resolution is fixed and deterministic.

For one managed execution request:

1. if a rule matches both `operation` and `purpose`, use that rule
2. else if a rule matches `operation` with `purpose = null`, use that rule
3. else if `chat_default_profile_id` is set, use it
4. else use the runtime catalog default profile for capability `chat`

There is no other fallback and no score-based ranking.

This keeps routing perfectly explainable.

---

## 5. Examples

### 5.1 Team-wide default

```yaml
team_id: bid-and-capture
version: 1
chat_default_profile_id: default.chat.mistral
operation_rules: []
```

Result:

- every managed chat phase in this team uses `default.chat.mistral`
- unless runtime deployment default must be used because the field is null

### 5.2 Planning override

```yaml
team_id: bid-and-capture
version: 2
chat_default_profile_id: default.chat.mistral
operation_rules:
  - rule_id: planning.high-quality
    operation: planning
    target_profile_id: chat.openai.gpt5
```

Result:

- general team traffic uses `default.chat.mistral`
- planning uses `chat.openai.gpt5`

### 5.3 Purpose-refined rule

```yaml
team_id: bid-and-capture
version: 3
chat_default_profile_id: default.chat.mistral
operation_rules:
  - rule_id: planning.default
    operation: planning
    target_profile_id: chat.openai.gpt5mini
  - rule_id: planning.gap-analysis
    operation: planning
    purpose: gap_analysis
    target_profile_id: chat.openai.gpt5
```

Result:

- `planning + purpose=gap_analysis` uses `chat.openai.gpt5`
- other planning uses `chat.openai.gpt5mini`
- everything else uses `default.chat.mistral`

---

## 6. Authorization

**Corrected 2026-07-10 for consistency with the shipped design** (renamed per
`FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` §26; the write rule below was also
substantively wrong — see the note under Business rule).

Read:

- `team_admin`
- `team_editor`

Write:

- `team_editor` only

Business rule:

- routing policy is a business-owned team behavior surface
- `team_admin` and `team_editor` are **orthogonal, not hierarchical**
  (`platform/REBAC.md` "hard cross-write rule", `FRED-TEAM-CONFIG-RFC.md` §7.2):
  `team_admin` has **zero write authority** over routing policy. The original
  draft's "owner supersedes manager" escalation was never implemented and
  contradicts the locked design rule — `team_admin` can only constrain
  `team_editor` indirectly, via `TeamPlatformPolicy` limits (§7 below), never
  by writing `TeamRoutingPolicy` directly.

---

## 7. Binding to platform policy

`TeamRoutingPolicy` is always bounded by `TeamPlatformPolicy`.

Required rule:

- every `chat_default_profile_id` and every `target_profile_id` must belong to
  `TeamPlatformPolicy.model_guardrails.allowed_profile_ids` when that allowlist
  is non-null

Rejected in V1:

- a routing policy that references a profile forbidden by platform policy

Platform policy is therefore the hard ceiling. Routing policy is only the
business choice inside that ceiling.

---

## 8. Runtime contract

Control-plane remains the source of truth for team-owned routing policy.

Runtime remains the source of truth for:

- model profile definitions
- deployment defaults
- actual model client construction

The two layers meet through an execution-time snapshot.

### 8.1 Required future contract extension

`ExecutionPreparation` must gain a routing snapshot field for managed execution.

Example shape:

```python
class TeamRoutingSnapshot(BaseModel):
    team_id: TeamId
    chat_default_profile_id: str | None = None
    operation_rules: list[TeamOperationRouteRule] = []
```

Then:

```python
class ExecutionPreparation(BaseModel):
    ...
    team_routing_snapshot: TeamRoutingSnapshot | None = None
```

### 8.2 Runtime merge rule

For one managed turn:

- static runtime catalog still provides profile definitions and deployment
  defaults
- `team_routing_snapshot` overlays the team-specific default and operation rules
- runtime validates every referenced `target_profile_id` against its local
  catalog before execution starts

### 8.3 Drift rule

If the snapshot references an unknown profile ID for that runtime deployment:

- execution must fail with an explicit drift/configuration error
- runtime must not silently fall back to another profile

---

## 9. Profile-ID contract

V1 requires profile IDs used by team routing policy to be deployment-global
identifiers, not pod-local labels.

That means:

- `chat.openai.gpt5`
- `default.chat.mistral`

are treated as stable product identifiers that can be referenced safely from
control-plane storage.

This RFC does not allow team routing policies to reference raw provider/model
pairs directly.

---

## 10. API contract

Future API surface:

```text
GET   /control-plane/v1/teams/{team_id}/routing-policy
PATCH /control-plane/v1/teams/{team_id}/routing-policy
```

Rules:

- `GET` returns the stored policy or an empty policy that resolves to runtime
  defaults
- `PATCH` is a full typed replacement in V1
- `PATCH` validates against `TeamPlatformPolicy`

No generic key-value tuning surface is allowed here.

---

## 11. Explicit non-goals for V1

V1 does not include:

- per-agent routing rules
- per-user routing rules
- model temperature or timeout tuning at team level
- browser-side model selection
- direct editing of runtime `models_catalog.yaml`

Those can be considered only after team default plus operation override semantics
have proven sufficient.
