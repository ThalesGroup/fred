# RFC — Team Routing Policy

**Status:** Shipped 2026-07-30 (issue #2118, rewritten 2026-07-26 on top of
the shipped models-as-capability system, issue #2110, `AGENT-CAPABILITY-RFC.md`
§8.7). §13's frontend picker landed 2026-07-30 via the follow-up
`available-models` endpoint (issue #2167) — #2118 shipped free-text profile
inputs with server-side-only validation first; §13 now matches the code. The
original 2026-05-23 draft predates the models-as-capability system and
proposed a second, parallel guardrail object
(`TeamPlatformPolicy.model_guardrails`) and a per-turn snapshot contract that
would now contradict the security posture
`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md` already locked in. See §7 and §8
for what changed and why; §3, §5, §9, §10 are materially unchanged from the
original.
**Author:** Dimitri Tombroff  
**Date:** 2026-05-23 (rewritten 2026-07-26)
**Area:** `control-plane-backend`, `fred-runtime`, `frontend`  
**Related:** `FRED-TEAM-CONFIG-RFC.md`, `TEAM-PLATFORM-POLICY-RFC.md`
(§7.1 there is superseded by §7 here), `AGENT-CAPABILITY-RFC.md` §8.7,
`docs/swift/platform/LLM_ROUTING_FRED.md`

---

## 1. Problem

Fred runtime already supports policy-based model routing by team and operation
(`libs/fred-runtime/fred_runtime/model_routing/`), and — as of #2110 — a
platform admin can already enable/disable individual models per team or
personal space (`kind="model"` capability, ReBAC `can_use`, enforced fail-closed
at `provider.py::build_for_chat`). What is still missing is the product layer
that lets a team (or a user, for their own personal space) *choose which of
the models available to them* is the default, and override that choice for
specific operations such as `planning`.

The target product behavior is simple:

- a team can define one default model profile for managed execution
- a team can override that default for specific operations such as `planning`
- those overrides can only ever reference models the team/personal space is
  already allowed to use (§7) — this feature never grants new model access,
  it only lets the holder of existing access express a preference among it

Without a dedicated team routing object, model selection risks being spread
across:

- pod-local YAML only
- per-agent tuning fields
- frontend assumptions
- undocumented conventions

This RFC defines the first product version of team routing policy.

**Personal spaces are in scope, not a special case.** A personal team
(`personal-<uid>`) already holds an implicit `team_editor` relation for its
owner (`teams/system.py::build_personal_team`, `my_relations=[TEAM_EDITOR]`),
so it satisfies the write-authorization rule in §6 through the same
mechanism as any other team — no personal-space branch anywhere in this
design. "Use the mock model for my personal space" and "this team defaults
to `chat.openai.gpt5mini`" are the same feature applied to a different
`team_id`.

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

V1 does not expose per-user (i.e. one member's individual override *inside a
shared, multi-member team*) or per-agent routing — see §11 for the precise
boundary, which is not the same thing as personal-space support above.

This is enough to cover the primary use cases:

- "all agents in this team use model X"
- "all planning phases in this team use model Y"
- "my personal space uses the mock model for testing"

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
- all profile IDs must be `can_use`-enabled for this team (§7 — model
  capability enablement, not a platform-policy allowlist)

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
`platform/REBAC.md`; the write rule below was also
substantively wrong — see the note under Business rule).

Read:

- `team_admin`
- `team_editor`
- `team_analyst` — added 2026-07-30 (#2167 follow-up), matching the frontend's
  `hasElevatedTeamRole` gate on the same "Routing" tab (`TeamSettingsPage.tsx`)
  and `TeamSettingsRouting`'s pre-existing `canWrite`-gated read-only
  rendering for non-editors. Implementation note: the service layer checks
  `can_read_members` first (team existence + minimum membership, shared
  plumbing also used by KPI scope/task activity/corpus manager — deliberately
  not narrowed, since narrowing it would change those unrelated surfaces
  too), then a routing-policy-specific `_require_elevated_team_role` check
  narrows to these three roles specifically. A plain `team_member` is denied.

Write:

- `team_editor` only

Business rule:

- routing policy is a business-owned team behavior surface
- `team_admin` and `team_editor` are **orthogonal, not hierarchical**
  (`platform/REBAC.md` "hard cross-write rule", `FRED-TEAM-CONFIG-RFC.md` §7.2):
  `team_admin` has **zero write authority** over routing policy. `team_admin`
  can only constrain `team_editor` indirectly, via model enablement (§7 below,
  a platform-admin lever, not a `team_admin` one), never by writing
  `TeamRoutingPolicy` directly.
- on a personal team the owner already holds `team_editor` unconditionally
  (`teams/system.py::build_personal_team`), so this rule needs no personal-
  space carve-out: the same `PATCH /teams/{team_id}/routing-policy` in §10
  serves both.

**Implementation prerequisite, reassessed 2026-07-26:** the original draft
blocked this work on `TEAM-02` ("authorization hardening for team-scoped
configuration surfaces", `id-legend.yaml`, no RFC — a five-item backlog note,
recoverable only from git history: agent-instance write auth, prompt-CRUD
write auth, session-route auth, unscoped personal-prompt lookups, and role
tests). Items 1-2 are the only ones this feature's write endpoint would touch,
and both are now already-established, reused patterns —
`product/api.py` gates agent-instance writes on `CAN_UPDATE_AGENTS` and prompt
writes on `CAN_UPDATE_RESOURCES` via `get_team_by_id_from_service(...,
required_permissions=[...])`, the same chokepoint shape as
`kpi/scope.py::resolve_kpi_scope`. A `TeamRoutingPolicy` write endpoint reuses
that pattern directly with `required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES]`
(the same permission that already resolves to `team_editor`-only, schema.fga
line 140). **TEAM-02 is no longer a hard blocker for this RFC** — items 3-4
(session-route authz, unscoped personal-prompt lookups) are real but
orthogonal to routing policy and can proceed independently.

---

## 7. Binding to model enablement (supersedes `TeamPlatformPolicy.model_guardrails`)

**Rewritten 2026-07-26.** The original draft bounded `TeamRoutingPolicy` by a
new `TeamPlatformPolicy.model_guardrails.allowed_profile_ids` object
(`TEAM-PLATFORM-POLICY-RFC.md` §3, §7.1) that did not exist yet. It does not
need to be built: the models-as-capability system shipped in #2110
(`AGENT-CAPABILITY-RFC.md` §8.7) already answers "which models may this team
use" — a platform admin enables/disables each model per team or personal
space today, in `/admin/capabilities?kind=model`, enforced via ReBAC `can_use`
grants on `model__<provider>__<name>` capability ids. Reusing it here means:

- no second guardrail object to keep in sync with the first
- one enable/disable action (already shipped, already has a UI) governs both
  "can this team's agents call this model" (today) and "can this team's
  routing policy reference this model" (this RFC) — the same permission,
  never two
- the existing fail-closed runtime check
  (`model_routing/provider.py::build_for_chat`, raises `ModelNotUsableError`)
  remains the last line of defense regardless of what a routing policy says —
  see §8.4

### 7.1 The id-space translation this requires

Model capability ids are keyed on `(provider, name)` only — one entry per
distinct model, not per `models_catalog.yaml` profile
(`fred_sdk/contracts/capability/manifest.py::model_capability_id`). A routing
policy's `target_profile_id` is a profile id, a finer-grained identifier: two
profiles can share the same `(provider, name)` with different settings (e.g.
different `temperature`), and both collapse to the same capability id. This
is an intentional, already-documented property of the capability system, not
a gap this RFC needs to close — it just means enablement is checked at
`(provider, name)` granularity even though the routing policy picks at
`profile_id` granularity:

```
target_profile_id → (catalog lookup) → ModelConfiguration(provider, name)
                   → model_capability_id(provider, name)
                   → must be can_use-enabled for this team_id
```

### 7.2 Write-time validation

`PATCH /teams/{team_id}/routing-policy` (§10) rejects any
`chat_default_profile_id` or `target_profile_id` whose derived capability id
is not currently `can_use`-enabled for `team_id` — reusing the same
`usable_capability_ids` lookup control-plane's `capabilities/authz.py`
already exposes (the same one `CapabilitiesPage`/`CapabilityTeamMatrixDrawer`
already query to show what's enabled). No new enablement check is invented;
this RFC only adds a new *caller* of the existing one.

It also rejects any profile id not present on **every** enabled,
model-capable pod (`capabilities/catalog.py::universally_available_model_profile_ids`,
2026-08-02, MDL#2 — see §9). §7.1's aggregated catalog unions profile ids
across pods for admission purposes ("does at least one pod know this
profile"), which is the wrong question here: whichever pod ends up serving a
turn must resolve the chosen profile, or it fails closed at runtime (§8.4).
Validating against the intersection instead of the union means a write that
succeeds can never drift-fail later on a pod that lacks it. The
`available-models` picker (§13) applies the same filter, so it never offers
an option the write would then reject.

Rejected in V1:

- a routing policy that references a profile the team is not allowed to use
- a routing policy that references a profile not deployed on every pod

---

## 8. Runtime contract

Control-plane remains the source of truth for team-owned routing policy.

Runtime remains the source of truth for:

- model profile definitions
- deployment defaults
- actual model client construction

The two layers meet through a session-preparation snapshot — **not** a
per-turn live lookup. §8.1 explains why this differs from how model
*authorization* works, which is the opposite of what the original draft
assumed.

### 8.1 Why this is a session-prep snapshot, not a per-turn snapshot

The original draft (§8.1, pre-2026-07-26) modeled this after what it assumed
`usable_model_ids` (the model-enablement check, §7) already did: a
control-plane-computed value threaded through `ExecutionPreparation`. That
assumption was wrong on inspection — `usable_model_ids` is in fact computed
**live, per turn, inside fred-runtime itself**
(`agent_app.py` around the per-turn handler, `model_routing/authz.py::usable_model_capability_ids`),
not snapshotted by control-plane at session prep. Two reasons, both specific
to *authorization*, neither of which applies to routing *preference*:

- `EXECUTION-GRANT-SECURITY-HARDENING-RFC.md` already rejected a
  control-plane-signed/cached-grant design for capability authorization in
  favor of live per-request pod-side ReBAC checks — a security boundary must
  never be stale.
- `ChatModelFactoryPort.build()` is synchronous, so the enforcement point
  structurally cannot `await` a fresh check inline — it must receive an
  already-resolved value, computed as close to call time as the sync boundary
  allows (once per turn).

`TeamRoutingPolicy` is not a security boundary — it is a business preference
about *which allowed model to prefer*. Staleness here costs nothing more than
"this turn used yesterday's preferred model" — never an authorization
violation, because §8.4's fail-closed check still runs regardless of what the
routing policy says. That makes the actual existing session-prep precedent
the right fit: `ExecutionPreparation` already carries `chat_controls`,
`context_prompt_text`, and `capability_base_urls`
(`product/schemas.py:291-357`) — control-plane-resolved once when a session
is prepared, not re-fetched per turn. This RFC follows that pattern, adding
one more field to the same object instead of inventing a new per-turn
channel (which would also add another live network hop to the model-authz
hot path already flagged in
`docs/swift/reviews/performance/2026-07-26-observ-02-v3/PERF-02-model-authz-openfga-hot-path.md`).

### 8.2 Contract extension — the actual three-hop channel

`context_prompt_text` is not a direct control-plane→runtime channel — tracing
it end to end shows control-plane resolves it into `ExecutionPreparation`,
the **frontend** folds it onto `RuntimeContext` via
`mergeContextPromptText()` (`rework/core/utils/runtimeStream.ts`) once when a
session starts, and every subsequent turn's request in that session carries
the same `RuntimeContext` value forward — fred-runtime just reads it off
`ctx.get("context_prompt_text")` per turn
(`agent_app.py` around the per-turn handler). This RFC's two new fields
follow the identical three-hop path, not a new one:

```python
# control_plane_backend/product/schemas.py — ExecutionPreparation
class ExecutionPreparation(BaseModel):
    ...
    chat_default_profile_id: str | None = None
    operation_route_rules: list[TeamOperationRouteRule] = Field(default_factory=list)
```

```python
# fred_sdk/contracts/context.py — RuntimeContext, new Group-C-style fields
class RuntimeContext(BaseModel):
    ...
    chat_default_profile_id: str | None = None
    operation_route_rules: list[TeamOperationRouteRule] = Field(default_factory=list)
```

Frontend gains a `mergeRoutingPolicy()` next to `mergeContextPromptText()`,
called at the same call site (`actions.ts` — `mergeContextPromptText({
...runtimeContext, team_id }, prep.context_prompt_text)` becomes a small
chain of both merges). Resolved by control-plane from the team's stored
`TeamRoutingPolicy` (or `None`/`[]` when the team has none) at the same point
`chat_controls` and `context_prompt_text` are resolved — prepare-execution,
once per session, not re-fetched per turn. This reuses an existing,
already-shipped channel; it does not add a new control-plane↔runtime
integration point, and it does not touch the per-turn OpenFGA path §7/§8.4
already uses for enablement.

### 8.3 Runtime merge rule

Per turn, fred-runtime reads `chat_default_profile_id` and
`operation_route_rules` off `RuntimeContext` (unchanged since session start —
see §8.2) and folds them into the `ModelRoutingResolver` it builds for that
request:

- `chat_default_profile_id`, if set, overrides `default_profile_by_capability["chat"]`
  for this session only — the static catalog default is unchanged for every
  other team
- the static YAML `rules:` are evaluated exactly as today, unchanged, and
  **always take precedence when one matches** — this is a deliberate ops
  escape hatch (e.g. force everyone off a broken provider platform-wide
  during an incident) that a team's own policy can never override
- only when the static resolver falls through to its capability default
  (`ModelSelectionSource.DEFAULT` — no static rule matched) does the team
  policy apply, as a second, narrower resolution pass: an
  `operation`(+`purpose`)-matching `TeamOperationRouteRule` wins, else
  `chat_default_profile_id` if set, else the static catalog default stands.
  This is new logic (a second small resolution step in `provider.py`
  reusing `resolver.py`'s existing specificity/order tie-break, not a
  rewrite of it) — the "no new object" claims in §7 do not extend to this
  method being literally unchanged
- runtime validates every referenced `target_profile_id` against its local
  catalog before execution starts

### 8.4 Drift and fail-closed rules

Two independent checks, never merged into one:

- **Unknown profile drift:** if the snapshot references a profile id absent
  from this runtime deployment's catalog, execution fails with an explicit
  drift/configuration error — no silent fallback to another profile.
- **Enablement fail-closed (unchanged, already shipped):** whatever profile
  the resolver ultimately picks — team default, operation override, or
  static deployment default — still passes through the existing
  `usable_model_ids` check in `build_for_chat`. If a team's routing policy
  references a profile that was enabled when the policy was written but has
  since been disabled by a platform admin, this is what catches it:
  `ModelNotUsableError`, not a silent substitution. Routing preference can go
  stale (§8.1); authorization never does.

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

Until 2026-08-02 this was a naming convention only — write-time validation
(§7.2) checked a profile id against the union of every pod's catalog, so a
profile registered on only one pod still passed as "known". §7.2 now
enforces the "deployment-global" claim for real: a profile must be on every
pod to be writable into a team's policy.

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
- `PATCH` validates every referenced profile against model enablement (§7.2),
  not against a separate platform-policy object

No generic key-value tuning surface is allowed here.

---

## 11. Explicit non-goals for V1

V1 does not include:

- **per-agent routing rules** — one team, one routing policy; an agent cannot
  carry its own override
- **per-user routing rules inside a shared, multi-member team** — this is
  distinct from personal-space support (§1): a personal team's routing policy
  is a *team* routing policy like any other, scoped to a `team_id` that
  happens to have one member. What stays out of scope is letting one member
  of a five-person team set a routing preference that only applies to them
- model temperature or timeout tuning at team level
- browser-side, per-message model selection in the chat composer (this RFC's
  UI is a team/personal-space *settings* surface, not a per-turn picker)
- direct editing of runtime `models_catalog.yaml` from the product

Those can be considered only after team default plus operation override semantics
have proven sufficient.

---

## 12. Relationship to the platform-admin surface

The platform-admin side of "LLM policy routing" is, after §7's rewrite,
almost entirely already shipped:

- **Which models a team/personal space may use at all** — `/admin/capabilities?kind=model`,
  enable/disable per team, `default_on`, `personal_scope` (#2110). Nothing
  new needed here; this RFC only adds a new consumer of the existing
  enablement data (§7.2).
- **The deployment-wide default model per capability** — today this is
  `default_profile_by_capability` in the static `models_catalog.yaml`, config
  file only, requires a pod redeploy to change. Whether to expose this as a
  control-plane-stored, platform-admin-editable override (following the same
  session-prep-snapshot shape as §8) is a small, separate, genuinely optional
  V1.1 slice — it is not required to ship team/personal routing policy, and
  should not block it. Tracked as an open question, not committed scope.

No new `TeamPlatformPolicy`-shaped object is needed for either.

---

## 13. Frontend surface

One panel, one component, reused for both team and personal space exactly
like `TeamUsagePage` already is (OBSERV-02 v3, #2110):

- **Entry point:** a "Routing" (or "Model") entry in the team settings
  navigation (`TeamContentNavbar.tsx`'s `settingsItems`), gated on
  `canUpdateResources` (`team_editor`) — the same gate already used for the
  "Usage" entry added in #2110, same file, same list. For a personal space,
  `canUpdateResources` is granted unconditionally (§1), so the entry appears
  there too with zero extra branching — do not special-case `isPersonalTeam`
  here; §7.1 established the enablement check already handles it uniformly.
- **Content:** a picker for `chat_default_profile_id` scoped to only the
  profiles whose derived capability is `can_use`-enabled for this team
  (§7.1). Shipped via a dedicated team-facing read endpoint,
  `GET /teams/{team_id}/routing-policy/available-models` (#2167) — not a
  reuse of `CapabilityTeamMatrixDrawer`'s data, which is platform-admin-only
  (`capability#can_manage`) and cannot back a team-scoped picker; the new
  endpoint shares the same `team_admin`/`team_editor` read gate as `GET
  .../routing-policy` and the same catalog-aggregation +
  `usable_capability_ids` building blocks the write path already validates
  against (§7.2). Zero or more operation-rule rows (`operation`, optional
  `purpose`, `target_profile_id`), same enabled-profile constraint per row.
  A profile id referenced by a stored policy that has since become
  unavailable (e.g. its capability was disabled) still renders as a
  selectable option, flagged rather than silently dropped from the list.
- **Read-only view for `team_admin`:** per §6, `team_admin` reads but never
  writes; render the same panel with inputs disabled rather than a second
  read-only component.
- Not shown when the team has no enabled models beyond the deployment
  default — an empty enablement list means there is nothing to choose
  between yet, so the panel should say so rather than render an empty
  picker.
