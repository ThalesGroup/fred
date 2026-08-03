# RFC: Model Reasoning Enablement — declaring, activating and toggling Thinking

**ID:** REASON-01
**Author:** Timothé Le Chatelier
**Status:** **Implemented (2026-07-30)** — all four levels shipped, plus the
three §9 preconditions. Phase 1 (levels 1-2) landed 2026-07-29; phase 2
(levels 3-4) landed 2026-07-30. All design decisions resolved 2026-07-29.
Amendment C (2026-08-02) relocated the level-3 form control; see below.

**Read §15 first if you are here for levels 3-4, then §17.** Amendment A
withdraws §7's central premise: reasoning is NOT a capability, so it
contributes no `turn_options` and no capability middleware. §17 (Amendment C)
later moved the level-3 toggle's on-screen location back into the (by then
renamed) Capabilities tab without reopening that conclusion. §14 records three
smaller places where the implementation had to deviate; §12 records the
questions the work closed.
**Tracking:** GitHub #2166, #2175 (Amendment B) — milestone `swift ga`
**Date:** 2026-07-29 (implementation notes 2026-07-30)
**Last amended:** 2026-08-02 — §17 (Amendment C): the level-3 toggle is
displayed in the agent form's Capabilities tab, using the same card chrome as
a real capability, following that tab's rename from Tools
**Track:** model routing / capability authoring / chat composer

---

## 0. As built

Frozen-contract entries: `RUNTIME-EXECUTION-CONTRACT.md` §8.29 / §8.30,
`CONTROL-PLANE-PRODUCT-CONTRACT.md` §32.

**Phase 1 (levels 1-2), 2026-07-29:**

| RFC section | Built as |
| ----------- | -------- |
| §4 / §4.3 | `ModelProfile.supports_thinking` + boot validator (`model_routing/contracts.py`); declared on `chat.mistral.small` only — the one profile in `models_catalog.yaml` that actually ships `reasoning_effort` |
| §5.3 | `_ModelCatalogEntry.thinking_profile_ids` (`agent_app.py`) → `CapabilityCatalogEntry.model_thinking_profile_ids` (fred-sdk) |
| §5.5 | `model_reasoning` table (migration `a7c3d91f2b40`) + `PATCH /admin/capabilities/{id}/reasoning`; snapshot on `ExecutionPreparation.reasoning_enabled_model_ids` → `RuntimeContext.reasoning_enabled_model_ids` |
| §5.6.1 | Release note added (`apps/frontend/public/release.md`, Unreleased → Breaking changes) |
| §5.6.2 | `without_reasoning_settings` applied in `RoutedChatModelFactory.build_for_chat`; proven against the real `ChatOpenAI` request payload in `libs/fred-runtime/tests/test_model_reasoning_enablement.py` |
| §5 admin UI | Reasoning column on the models view of `CapabilitiesPage`, rendered only when `thinking_profile_ids` is non-empty |

**Phase 2 (levels 3-4 + the §9 preconditions), 2026-07-30:**

> **Reasoning is NOT a capability.** §7 proposed shipping levels 3-4 as a
> `reasoning` capability. It was built that way, then withdrawn on the
> developer's decision (2026-07-30) before release — see **§15**. Reasoning is a
> property of *how the model is called*, not a tool an agent uses, so putting it
> in the tool picker asked authors to enable it in the wrong mental model. The
> rows below describe what actually ships. **§17 (Amendment C, 2026-08-02)**
> later moved this control's on-screen location into the Capabilities tab
> (renamed from Tools) without reopening this conclusion — see that section.

| RFC section | Built as |
| ----------- | -------- |
| §6 (level 3) | `AgentTuning.reasoning_enabled` / `ManagedAgentTuning.reasoning_enabled` — a plain agent property. Displayed in the agent form's **Capabilities tab** since §17 (Amendment C, 2026-08-02), using the same card chrome as a real capability; still no capability underneath. Enforced pod-side by intersecting it into the level-2 ceiling (§14.5), not only by hiding the composer control |
| §5.7 | Switching a model off (default-on → off) switches its stored `reasoning_enabled` off with it; reported on `CapabilityDefaultOnResult.reasoning_disabled` |
| §7 (level 4) | `RuntimeContext.reasoning` (tri-state `bool \| None`), a platform chat option travelling per turn exactly like `search_policy`/`search_rag_scope` — not a capability `turn_options` slice |
| §7.3 | Not needed. Level 4 is enforced at the SAME point as level 2 (`build_for_chat`, on `ModelConfiguration.settings`), so there is no built client to patch and neither `.bind` nor `model_copy` is involved — see §15 |
| §7.4 | `reasoning` joins `ComposerState` (`useComposerSettings`); `reasoning_toggle` stock control, rendered as a **switch** row (`MenuPopoverItem trailingToggle`) so the one setting looks the same in the composer, on the agent form and on the admin models page; value folded onto `RuntimeContext` by `buildComposerRuntimeContext` |
| §8 | `_platform_reasoning_control` (`product/service.py`) — control-plane EMITS the descriptor when every gate is open, rather than filtering one a capability produced |
| §9 precond. 1 | `fred_agents/tool_pacing.py` — `max_tool_calls_per_turn=12` on all five ReAct agent policies |
| §9 precond. 2 | `TOOL_REPETITION_RULE` in `build_runtime_tool_prompt_suffix` (`react_tool_binding.py`) + two tests in `test_react_prompting.py` naming reasoning drift |
| §9 precond. 3 | `ToolSelectionPolicy` docstrings corrected (cap is enforced; `allow_parallel_calls` documented as declarative-only) |

One deployment choice worth recording, which changes nothing in the design:
**only `chat.mistral.small` declares `supports_thinking`.** Other catalog models
(GPT-5.x, Claude Sonnet) are reasoning-capable in the abstract but ship no
reasoning setting, so declaring aptitude for them would surface a toggle with
nothing to switch (see §14.3). Adding one is a single YAML line plus an
`reasoning_effort` value.

---

**Related, and deliberately not duplicated:**

- `AGENT-THINKING-API-RFC.md` (RUNTIME-04/05) — owns how reasoning is **surfaced**
  (`THOUGHT_*` events, `context.thinking()`, provider passthrough). Owns nothing
  about whether reasoning is on.
- `AGENT-THINKING-API-RFC.md` Amendment C (2026-07-29) — the measured behaviour of
  reasoning on a tool loop. §9 of this RFC is a direct consequence of it.
- `CONTROL-PLANE-PRODUCT-CONTRACT.md` §37 — owns "which models may this team use",
  and owns the `(provider, name)` id granularity this RFC must live with.
- `AGENT-CAPABILITY-RFC.md` §8.7 — owns the `kind="model"` capability projection.
- `CHAT-COMPONENT-SPECS.md` §13 (CHAT-07, Implemented) — owns composer state.
- `docs/swift/issues/ISSUE-005-reasoning-model-redundant-tool-calls.md`.

---

## 1. Problem

Reasoning is enabled today by exactly one line of YAML:

```yaml
# apps/fred-agents/config/models_catalog.yaml
settings:
  reasoning_effort: high
```

`ModelConfiguration.settings` is `Optional[Dict[str, Any]]`
(`fred_core/common/structures.py:70`) — an untyped provider passthrough. Three
consequences follow, and they are the whole problem:

1. **Nothing in Fred knows a profile reasons.** No field, no type, no API response
   carries it. The control-plane cannot display it, the admin UI cannot gate it,
   the composer cannot offer it, no test can assert on it.
2. **Changing it requires a redeploy.** An ops decision frozen at pod boot,
   identical for every team, every agent, every question.
3. **"Model X reasons" is not currently a well-formed statement.** The catalog on
   this branch declares `mistral-small-latest` twice — `chat.mistral.small` with
   `reasoning_effort: high`, `language.mistral.small` without. Same
   `(provider, name)`, therefore the same capability id
   `model__openai__mistral-small-latest`, two different behaviours.

**The target behaviour**, as specified by the developer (2026-07-29): the admin
panel lists every model with a toggle activating its reasoning — present only for
models whose configuration declares they can reason, and switching it off disables
reasoning on that model for everyone; an agent author enables reasoning on an
agent at creation time; and an end user turns it on for a given question from the
composer before sending.

## 2. Why this is a new RFC and not a fourth amendment

`AGENT-THINKING-API-RFC.md` is ~1030 lines across three amendments and specifies
one thing well: how reasoning that *is happening* becomes visible. Whether it
happens at all has never been in scope — its §C.9 already names one such gap
(continuity back into the model) and explicitly declines to resolve it.

Enablement is a second, distinct gap, touching the routing layer, the capability
system and the composer — none of which the thinking RFC covers.

**Boundary, stated so the next reader sees it:** RUNTIME-04/05 own surfacing;
REASON-01 owns enablement; ISSUE-005 owns the tool-loop defect. A one-line pointer
should be added to `AGENT-THINKING-API-RFC.md` §7 — listed in §11, not applied
here (that file has uncommitted local edits).

---

## 3. The four levels

Conflating these is the main failure mode available here, so they are named. All
four must be true for reasoning to occur; each is owned by a different actor.

| # | Level | Question it answers | Who decides | Where it lives today |
| - | ----- | ------------------- | ----------- | -------------------- |
| 1 | **Aptitude** | does this *profile* support Thinking? | ops, in YAML, redeploy | nowhere — §4 |
| 2 | **Platform activation** | is reasoning on for this *model*, platform-wide? | platform admin, live | nowhere — §5 |
| 3 | **Agent configuration** | does this *agent* offer it? | agent author | mechanism exists — §6 |
| 4 | **Activation** | does the user want it *for this question*? | end user | mechanism exists, control does not — §7 |

Levels 1 and 2 are independent: a profile may *support* Thinking and ship with it
off, which is precisely the state levels 3–4 need in order to have something to
turn on.

**Level 2 is global, not per team** (decided 2026-07-29). This is a deliberate
simplification with a second, unplanned benefit: a live per-model off switch is
exactly the operational kill switch an earlier draft proposed platform-wide and
then dropped for lack of an identified need. §9 shows why that matters — it is
the only lever that can stop a reasoning-induced incident without a redeploy.

---

## 4. Level 1 — declare aptitude on the profile

**Decided (2026-07-29):** profile granularity, and the declaration says only
whether Thinking is *supported*.

Profile rather than model, because that is where the behaviour actually differs —
the same `(provider, name)` reasons in one profile and not the other on this very
branch. A model-keyed aptitude flag would be a statement the catalog contradicts.

### 4.1 Proposed shape (option A — recommended)

One field on `ModelProfile` (`fred_runtime/model_routing/contracts.py:179`):

```python
class ModelProfile(FrozenModel):
    profile_id: str = Field(..., min_length=1)
    capability: ModelCapability
    model: ModelConfiguration
    description: str | None = None
    supports_thinking: bool = False   # NEW — declared aptitude, not activation
```

```yaml
- profile_id: chat.mistral.small
  capability: chat
  supports_thinking: true
  model:
    provider: openai
    name: mistral-small-latest
    settings:
      base_url: https://api.mistral.ai/v1
      reasoning_effort: high
```

On `ModelProfile` and **not** on `ModelConfiguration`: the latter lives in
`fred-core`, shared with knowledge-flow and every other service, none of which has
an opinion about agent reasoning. `ModelProfile` is the routing-layer object and
is already what the catalog advertises.

### 4.2 Alternatives

| Option | Shape | Verdict |
| ------ | ----- | ------- |
| **A** | `supports_thinking: bool` | **Recommended** — matches the decision taken; one additive field with a safe default, no migration |
| B | `thinking: ThinkingSpec \| None` carrying `supported`, `effort`, `default_on` | More expressive; needed only if a user-facing effort picker is requested (§12 q3). `effort` can stay in `settings` until then |
| C | Derive it: `"reasoning_effort" in settings` | **Rejected** — conflates aptitude with activation. A profile supporting Thinking but shipping it off would be indistinguishable from one that cannot do it, destroying levels 3–4 |

### 4.3 Consistency validation (fail loud at config load)

Declaring `reasoning_effort` in `settings` while `supports_thinking` is false is
always an authoring mistake. It must fail at pod boot with a named error, in the
spirit of the existing `ModelProfile.validate_model` validator — not be silently
tolerated, which is how the current opaque-dict situation arose.

The converse (`supports_thinking: true`, no `reasoning_effort`) is **legal and
meaningful**: supported, off by default, available to levels 3–4.

---

## 5. Level 2 — platform activation, per model, global

**Decided (2026-07-29):** the admin panel lists every model; each model carries a
toggle activating or deactivating its reasoning. The toggle is **present only if
the model's configuration declares that it can reason** (§5.3). Turning it off
disables reasoning on that model **for everyone** — it is a platform decision, not
a per-team grant.

### 5.1 Not an authorization — an activation

This is worth stating precisely, because the natural instinct is to reach for the
existing enablement system and that would be wrong here.

`CONTROL-PLANE-PRODUCT-CONTRACT.md` §37 (shipped, #2110) governs **who may use a model**:
ReBAC `can_use` grants on `model__<provider>__<name>`, per team, with a fail-closed
runtime check (`ModelNotUsableError`, `model_routing/provider.py:217`). That system
answers a different question and stays untouched.

Level 2 governs **how the model runs** when someone already allowed to use it does
so. It is not a permission, so it needs no subject, no team dimension and no ReBAC
relation. Building it as a grant would mean duplicating the `capability` type's
seven-relation enablement lattice (`enabled`, `disabled`, `inherited`, `default_on`,
`personal_grant`, `personal_block`, `personal_on`/`personal_disabled`, composed into
`can_use` at `schema.fga:284`) for an axis that has no per-subject semantics at all.

### 5.2 The granularity constraint it must respect

Model capability ids are keyed on `(provider, name)`; aptitude, per §4, is per
profile. `CONTROL-PLANE-PRODUCT-CONTRACT.md` §37 calls the coarser key *"an intentional,
already-documented property of the capability system, not a gap this RFC needs to
close"*, and ReBAC tuples are already written against those ids. **The id space is
not negotiable** — so the admin toggle must be keyed on the model, and §5.3 is how
per-profile truth is projected onto it.

### 5.3 Resolution — derived aptitude on the model catalog entry

The join already exists and is one line from being useful.
`_project_model_catalog_entries` (`fred_runtime/app/agent_app.py:992-1029`)
already groups profiles by `(provider, name)` and carries `profile_ids`. Extend
its entry with a **derived, read-only** field:

```python
class _ModelCatalogEntry(BaseModel):
    id: str
    provider: str
    name: str
    description: str | None
    profile_ids: list[str]
    thinking_profile_ids: list[str] = []   # NEW — subset with supports_thinking
```

One condition inside the existing loop. Semantics:

- `thinking_profile_ids == []` → this model has no reasoning-capable profile. The
  admin row shows **no reasoning control at all**. This is aptitude, not a choice —
  an administrator cannot make a model reason.
- non-empty → the model row carries the toggle. On means: *"this model's
  thinking-capable profiles may run with reasoning on"*. Off means they never do,
  for anyone, whatever levels 3 and 4 say.

**This is the resolution:** aptitude stays per profile (where it is true), the
toggle is keyed per model (where the id space and the admin UI both are), and the
mapping between the two is **derived, never authored twice**. `model_profile_ids`
on `CapabilityCatalogEntry` (`manifest.py:375`) already carries the same join to
control-plane for the routing policy — this reuses that established pattern.

### 5.4 Orthogonality — what this toggle does *not* touch

Stated because the two axes share a screen and will be confused otherwise:

| Axis | Question | Subject | Mechanism | Changed by this RFC |
| ---- | -------- | ------- | --------- | ------------------- |
| Enablement (existing) | may this team use this model at all? | a team | ReBAC `can_use` on `model__…` | **no** |
| Reasoning (this RFC) | does this model run with reasoning? | none — the model itself | §5.5 | yes |

Enabling a model for one team or for everyone is unaffected: the model is simply
enabled *with* or *without* reasoning, identically for whoever is allowed to use
it.

### 5.5 Storage and delivery

No platform-level settings store exists today — control-plane has no
`PlatformPolicy` class, and `TEAM-PLATFORM-POLICY-RFC.md` remains a Draft, partly
superseded. This level therefore needs one small piece of new persistence.

| Option | Mechanism | Verdict |
| ------ | --------- | ------- |
| **A** | One control-plane table keyed by model capability id (`model__<provider>__<name>` → `reasoning_enabled: bool`), one `PATCH` endpoint, read into the session-preparation snapshot | **Recommended** — smallest thing that works; no new id space, no new authority, one row per model |
| B | A ReBAC relation | Rejected — §5.1: no subject, therefore not a permission |
| C | Keep it in `models_catalog.yaml` | Rejected — a redeploy for every change is exactly what the toggle exists to avoid |

**Delivery to the runtime** reuses the established channel rather than inventing
one: the control-plane → runtime session-preparation snapshot
(`ExecutionPreparation`), the same three-hop path
`RUNTIME-EXECUTION-CONTRACT.md` §8.32 specifies for routing policy. A per-turn
live lookup is not needed for the same reason routing policy doesn't need one.

### 5.6 Default — off (decided 2026-07-29)

**A model with no stored toggle row does not reason.** Enabling a model and
enabling its reasoning are two separate admin actions, in that order; the second
is never implied by the first.

The alternative considered and rejected was falling back to the YAML's intent
(reasoning on iff the profile ships `reasoning_effort`). Off-by-default is chosen
on §9 grounds: a defect measured at 10/10 turns should not be inherited silently
by a deployment that upgrades.

### 5.6.1 Consequence — this level is NOT purely additive

Deploying level 2 **turns reasoning off** on any deployment currently running it
through YAML alone, until an administrator switches it on. On this branch that is
`chat.mistral.small`, the current `chat` default.

This is a behaviour change on upgrade and needs a release note, not a silent
rollout. Without one, the observed symptom is "reasoning stopped working after the
upgrade" with no visible cause.

### 5.6.2 Consequence — the toggle must be enforced at model construction

`reasoning_effort` lives inside `ModelConfiguration.settings`, which is handed to
the provider when the client is built. **A toggle that merely declines to add
`reasoning_effort` does nothing**, because the YAML already put it there — the
model would reason with the toggle off.

Enforcement must therefore *remove* `reasoning_effort` from the settings passed to
the client whenever the resolved toggle is off, in `model_routing/provider.py`, at
construction time.

This RFC states it explicitly because the codebase already contains the exact
failure it prevents: Amendment C §C.8 records `allow_parallel_calls` as
**"Decorative. Never reaches the model"** — a flag whose only production effect is
rendering a sentence into a prompt summary. A reasoning toggle that never reaches
the client would be the same bug, with an incident lever's name on it.

A test asserting that the constructed client carries no reasoning setting when the
toggle is off is the minimum bar for this level.

### 5.7 Switching a model off switches its reasoning off (2026-07-30)

§5.4 states the two axes are orthogonal. That holds in one direction only, and
this section records the exception the developer asked for after using the
screen:

- **enabling** a model does **not** enable its reasoning — unchanged, reasoning
  stays a deliberate second decision;
- **disabling** a model (default-on → off) **does** switch its stored
  `reasoning_enabled` off with it.

The asymmetry is not a hedge. A stored `reasoning_enabled` left behind on a
withdrawn model is a decision nobody can see: the row's reasoning switch is the
only trace, and re-enabling the model months later silently brings reasoning
back with it. Fail-closed matches §5.6's default — reasoning is never on because
of something that happened earlier and was forgotten.

Two constraints on the implementation:

- **no row is written when there was none.** An absent row and a stored `false`
  are the same state (§5.6); stamping a `false` row on every model an admin ever
  switches off would fill the table with rows meaning "default".
- **the cascade is reported, not silent.** `CapabilityDefaultOnResult.reasoning_disabled`
  tells the admin the row changed in two places, because the second change is
  visible in the UI a moment later and an unexplained one reads as a bug.

Note what this does *not* claim: default-off is not "no team can use this model"
— a team holding an explicit `can_use` grant keeps access. Reasoning can still be
switched back on for such a model; the cascade fires on the admin's withdrawal,
it does not make the state unreachable.

---

## 6. Level 3 — agent configuration

**Decided (2026-07-29).** This level was added by the developer and is a genuine
improvement on the first draft, because it is **the already-shipped canonical
pattern**, not a new mechanism.

`document_access` does exactly this today:

- `show_search_policy_control: bool = True` on the `ConfigModel`
  (`document_access/capability.py:273`), exposed as a `FieldSpec` on the
  agent-creation form (`capability.py:469`);
- `chat_controls()` returns the composer widget **only if that config field is
  true** (`capability.py:553`).

The `reasoning` capability therefore declares both typed models:

| Model | Field | Meaning |
| ----- | ----- | ------- |
| `ConfigModel` | `reasoning_enabled: bool = False` | agent author: does this agent offer reasoning at all |
| `TurnOptionsModel` | `reasoning: bool = False` | end user: is it on for this question |

`chat_controls(config)` returns the composer control only when
`config.reasoning_enabled` **and** the resolved profile declares
`supports_thinking`. A user never sees a toggle that cannot do anything.

---

## 7. Level 4 — user activation from the composer

### 7.1 The mechanical constraint, up front

Chat controls are contributed **only** by capabilities — verified:
`document_access/capability.py:553` and `mcp.py:255` are the two live sources.
There is no platform-level composer control mechanism.

A reasoning capability contributes **no tools** — reasoning is a model construction
parameter, not something an LLM calls. It is therefore `middleware()`-only, and
the boot invariant is mechanical, not advisory:

> a `middleware()`-only capability whose `execution_models` contains `"graph"` is
> refused at pod boot (`InvalidExecutionModelError`).

**Consequence, accepted 2026-07-29: levels 3 and 4 are reachable from ReAct agents
only.** The scope of that exclusion is narrower than it first appears, and the
distinction is what made it acceptable:

| Level | Graph agents |
| ----- | ------------ |
| 1 — aptitude (YAML) | applies |
| 2 — platform toggle | applies |
| 3 — per-agent config | **no** |
| 4 — per-question toggle | **no** |

Levels 1–2 live in the routing layer, which Graph agents traverse through the same
factory call (`graph/graph_runtime.py:1101` → `build_for_operation`). A Graph agent
on a thinking profile with the platform toggle on **does reason**; what it lacks is
the *choice* — no creation-time field, no composer control. Reasoning there is an
ops and platform-admin decision, not an author or user one.

Graph authors also retain `context.thinking()` (`AGENT-THINKING-API-RFC.md` §6) for
authored reasoning — the API that RFC designed for exactly this execution model.

Rationale for accepting: every tool-looping agent in `apps/fred-agents` is ReAct
(6 ReAct definitions vs 4 Graph, two of which are test harnesses), and the tool
loop is both where reasoning pays off and where Amendment C's defect lives.

### 7.2 The capability

| Element | Value |
| ------- | ----- |
| id | `reasoning` |
| kind | `tool` (the default; `"model"` is a reserved projection, never authored) |
| `execution_models` | `("react",)` — exactly, per the boot rule |
| `ConfigModel` | `reasoning_enabled: bool` (§6) |
| `TurnOptionsModel` | `reasoning: bool` (§6) |
| `TeamSettingsModel` | `EmptyModel` — level 2 is global and lives in control-plane (§5.5), not in per-team capability settings |
| `chat_controls(config)` | one `ChatControlSpec(widget="reasoning_toggle", params={"default": False})`, gated per §6 |
| `middleware()` | one `AgentMiddleware` overriding `awrap_model_call` |
| `team_scope` | `ADMIN_GATED` (the default) |

Placement is already correct: the capability slot sits after
`ModelRoutingMiddleware` in the frame (`react/middleware/frame.py:78-89`), so the
capability's `awrap_model_call` runs *inside* the routing one and its
`request.override(...)` wins. No frame reordering needed.

### 7.3 How the flip is performed

| Option | Mechanism | Verdict |
| ------ | --------- | ------- |
| **A** | `request.override(model=request.model.bind(reasoning_effort=effort))` | **Recommended** — no second client build, no cache to invalidate. **Conditional on a probe** (§12 q4): it must be verified that `ChatOpenAI` forwards a `bind` kwarg into the Mistral payload |
| B | Build a second client from a thinking profile via `ctx.services.chat_model_factory`, cached per operation as `ModelRoutingMiddleware` already does | Certain to work; heavier, duplicates a cache. Fallback if the A probe fails |

`chat_model_factory` is present on `RuntimeServices`
(`fred_sdk/contracts/runtime.py:835`), so both options are reachable from a
capability without violating the closure doctrine — the toggle travels through
`TurnOptionsModel`, never through a tool signature.

### 7.4 Frontend

`useComposerSettings` already persists composer state per session in
`sessionStorage` and reads widget defaults from the `chat_controls` descriptors
(CHAT-07 Step 5). A `reasoning` boolean joins `ComposerState`. Unknown widget ids
are silently skipped by the frontend, so the backend may ship first without
breaking any client.

---

## 8. Why a user's toggle may do nothing — the diagnosability requirement

Four gates now stand between a user and a reasoning turn: ops declared the profile
capable, the platform admin left the model's toggle on, the agent author enabled
it, the user flipped it. Each is owned by a different person, and three of them are
invisible from the chat page.

Without a rule, the predictable support ticket is *"I turned reasoning on and
nothing happened"*, with no way to tell which gate blocked.

**Requirement:** the composer control must be **absent** (not present-and-inert)
whenever any upstream gate is closed — which §6 already achieves, since
`chat_controls()` is computed at session prep with the config and the resolved
profile both in hand. Level 2's flag must reach that same computation through the
snapshot (§5.5), so a model switched off platform-wide also shows no control.

The one case this does not cover is a resolved profile changing mid-session
(routing picks a different profile per operation). Listed as §12 q5.

---

## 9. Safety — this feature widens exposure to a measured defect

Not precaution; a restatement of measurements taken today, on this stack, recorded
in `AGENT-THINKING-API-RFC.md` Amendment C.

| Measured fact (Amendment C) | Where |
| --------------------------- | ----- |
| `mistral-small` + reasoning on a tool loop: **10/10 turns with a duplicate tool call, 28 duplicate calls**; re-measured twice (16/16, 12/12) | §C.4 |
| Removing Fred's `strip_reasoning_from_history` changes **nothing** — `langchain-openai` filters `thinking` blocks outbound on both `chat/completions` and `responses` | §C.4 |
| The symptom is invisible in production **only** because of `build_tool_failure_recovery_suffix()`, written for issue #2073, with no test tying it to reasoning drift | §C.7 |
| `ToolCallLimitMiddleware` is wired (`frame.py:114-126`) but **inert** — `max_tool_calls_per_turn` defaults to `None`, no agent config sets it | §C.8 |
| Tool-call de-duplication: **absent** | §C.8 |

This RFC takes a setting confined to one YAML line and hands it to administrators,
agent authors and end users. It multiplies exposure to a defect currently
suppressed by accident.

**Level 2 is the mitigation, and this is its strongest justification.** A live,
per-model off switch (§5) means a reasoning-induced incident can be stopped in one
click, without a redeploy and without touching any agent or team. That is why §5.5
option C (keep it in YAML) is rejected on operational grounds and not merely on
convenience: an incident lever that requires a deploy is not a lever.

**Preconditions on levels 3–4 — not scope creep:**

1. **Activate the existing guardrail.** Set `max_tool_calls_per_turn` on
   reasoning-capable agent configs. Configuration, not code: the middleware is
   already wired and correctly placed.
2. **Make the anti-repetition guidance intentional.** Amendment C §C.10 q4 already
   proposes moving it into `build_runtime_tool_prompt_suffix()`
   (`react_tool_binding.py:98-105`). Add the regression test tying it to reasoning
   drift, so a future #2073 rewording cannot silently re-expose this.
3. **Fix the stale contract docstring.** `ToolSelectionPolicy`
   (`fred_sdk/contracts/models.py:797, 810-811`) still says the cap is "Reserved
   for now … does not enforce this limit yet", untrue since `frame.py` wired it.

**Level 1 carries none of this risk** — declaring aptitude changes no runtime
behaviour on its own. Level 2 does change behaviour — it turns reasoning **off**
until an admin acts (§5.6.1) — but it changes it in the safe direction, and it is
the incident lever itself. Shipping both before levels 3–4 puts the lever in place
*before* exposure widens.

---

## 10. Alternatives considered (whole-design level)

| Alternative | Verdict |
| ----------- | ------- |
| A new `ModelCapability.REASONING` enum value alongside `chat`/`language`/`embedding`/`image` | **Rejected.** That enum means "technical model family" (`contracts.py:166-171`). Reasoning is orthogonal to family — a reasoning chat model is still a chat model. Adding it would make every routing rule and `default_profile_by_capability` entry ambiguous |
| Keep YAML-only, no UI | **Rejected** — the status quo this request exists to change |
| Derive aptitude from a hardcoded model-name allowlist | **Rejected** — drifts with every provider release; the deployment already declares its own catalog |
| Give the capability a no-op tool to escape the ReAct-only lock | **Rejected** — pollutes the LLM tool schema with a non-tool; the boot rule exists precisely to make "contributes nothing to Graph" visible rather than silent |
| Make level 2 per team (enable/disable reasoning per team × model) | **Rejected 2026-07-29** — reasoning is a property of how a model runs, not a permission (§5.1). A per-team axis would have cost a `TeamSettingsModel`, a custom form widget for a deployment-dependent model list, and a team×model matrix, for a distinction nobody asked for |
| A deployment-wide master switch, all models at once | Considered and dropped as a separate mechanism: §5's per-model toggle already provides the incident lever (§9), at finer granularity and with no extra surface |

---

## 11. Impact

| Component | Change | Level |
| --------- | ------ | ----- |
| `fred_runtime/model_routing/contracts.py` | `supports_thinking: bool = False` on `ModelProfile` + consistency validator | 1 |
| `apps/fred-agents/config/models_catalog.yaml` | Declare `supports_thinking` on reasoning-capable profiles | 1 |
| `fred_runtime/app/agent_app.py` | `thinking_profile_ids` on `_ModelCatalogEntry`, derived in `_project_model_catalog_entries` | 2 |
| `control_plane_backend/product/service.py` | Carry `thinking_profile_ids` through the `kind="model"` projection | 2 |
| control-plane — new table + `PATCH` endpoint | `model_capability_id → reasoning_enabled`; absent row = off (§5.6) | 2 |
| `model_routing/provider.py` | Strip `reasoning_effort` from settings at client construction when the toggle is off, + the test that proves it (§5.6.2) | 2 |
| Release notes | Reasoning turns off on upgrade until an admin enables it (§5.6.1) | 2 |
| control-plane — `ExecutionPreparation` | Carry the resolved per-model reasoning flag to the runtime (§5.5) | 2 |
| `apps/frontend` — models admin page | One toggle per model row, rendered only when `thinking_profile_ids` is non-empty | 2 |
| New capability `reasoning` (class + entry point) | `ConfigModel`, `TurnOptionsModel`, `chat_controls`, `middleware()`, `execution_models=("react",)` | 3–4 |
| `apps/frontend` — composer | `reasoning_toggle` widget, `reasoning` in `ComposerState` | 4 |
| Agent configs | Set `max_tool_calls_per_turn` on reasoning-capable agents | 9 |
| `react_tool_binding.py` + new test | Make anti-repetition guidance intentional | 9 |
| `fred_sdk/contracts/models.py` | Fix stale `ToolSelectionPolicy` docstring | 9 |
| `AGENT-THINKING-API-RFC.md` §7 | One-line pointer to this RFC (surfacing vs enablement boundary) | — |
| OpenAPI + generated clients | Regenerate — `ModelProfile` and models-catalog shapes change | 1, 2 |

---

## 12. Remaining questions — implementation-level

**All design decisions were resolved 2026-07-29; every question below is now
closed by the implementation (2026-07-30).**

1. **Boolean, or an effort picker?** → **Boolean** (§4.2 option A, as
   recommended). `reasoning_effort` stays in `settings` as ops-authored data;
   option B's `ThinkingSpec` remains available if a user-facing picker is ever
   asked for. See §14.3 for what the boolean choice costs.
2. **Does `.bind(reasoning_effort=...)` reach the Mistral payload through
   `ChatOpenAI`?** → **Probed 2026-07-30. Yes for ON, but `.bind` cannot express
   OFF, so option A is not usable.** Binding kwargs are merged into
   `_get_request_payload` at call time, so `.bind(reasoning_effort="high")` does
   reach the wire. But `.bind(reasoning_effort=None)` puts
   `reasoning_effort: null` **on the wire** rather than omitting the field, and
   an explicit null is a different request. `model_copy(update={...: None})` on
   the client removes it cleanly and works in both directions, so that is the
   mechanism. Option B was unreachable anyway (§14.2).
3. **Mid-session profile change** → **Fail silently, deliberately, and prefer
   under-hiding.** The control is dropped only when NO model has its reasoning
   enabled platform-wide (`_drop_inert_reasoning_controls`). Narrowing to the
   profile a given turn will route to is not possible at session prep — routing
   resolves per operation at runtime — so a turn that routes to a non-thinking
   profile while the toggle is shown simply does not reason. Showing a control a
   later operation might not honour beats removing one that would have worked.
4. **Sequencing** → followed as recommended: levels 1-2 shipped first
   (2026-07-29), the §9 preconditions and levels 3-4 second (2026-07-30).

---

## 13. What this RFC does not do

- It does not change how reasoning is rendered — RUNTIME-04/05 own that, unchanged.
- It does not resolve reasoning **continuity** across the tool loop
  (`AGENT-THINKING-API-RFC.md` §C.9, ISSUE-005). That defect exists whether or not
  this RFC ships; §9 only requires that this RFC not make it worse unguarded.
- It does not modify model capability id granularity (§5.2).
- It does not change who may use which model — the existing per-team ReBAC
  enablement is untouched (§5.1, §5.4).
- It does not add a deployment-wide master switch: §5's per-model toggle already
  serves as the incident lever (§9).

---

## 14. Where the implementation deviates from this document (2026-07-30)

Recorded per `CLAUDE.md`'s rule that code and the frozen contract docs win over
an RFC, and that divergence must be flagged rather than quietly implemented.
None of these changes the agreed *design* — the four levels, their owners, and
level 2 as a global ceiling all stand. They change three *mechanisms* this
document named before the code was read.

### 14.1 §8's premise about `chat_controls` is false

§8 says the composer control can be hidden per gate "since `chat_controls()` is
computed at session prep with the config and the resolved profile both in hand".

It is not. The SDK signature is `chat_controls(self, config)` and nothing else
(`fred_sdk/contracts/capability/base.py`). A capability sees its own stored
config; it has no binding, no runtime context, no resolved profile — deliberately
(§3.5's closure doctrine). So the capability can enforce level 3 and only
level 3.

**As built:** the capability applies its own gate, and the platform gate is
applied control-plane-side at session prep by `_drop_inert_reasoning_controls`
(`product/service.py`), where the activation snapshot already is. §8's
*requirement* — absent, never present-and-inert — holds; only its stated
mechanism was wrong.

A pleasant consequence: no catalog fetch is needed on the send path, because the
write path already guarantees the aptitude half. `set_model_reasoning` 409s on a
model with no `supports_thinking` profile, so a stored enabled row can only name
a reasoning-capable model.

### 14.2 §7.3's two options were both unusable as written

- **Option A (`.bind`)** — the §12 q2 probe says `.bind` reaches the payload for
  ON but cannot express OFF: `.bind(reasoning_effort=None)` sends
  `reasoning_effort: null` rather than omitting the field. Since level 4's only
  reachable direction is removal (§14.3), option A cannot do the job.
- **Option B (`ctx.services.chat_model_factory`)** — unreachable from a
  capability. `ChatModelFactoryPort.build`/`build_for_operation` both require
  `definition` and `binding`, and `CapabilityContext` carries neither by design.
  The RFC assumed the port was callable with what a capability has; it is not.

**As built:** `model_copy(update={<key>: None})` on the resolved client, guarded
on the field being *declared* by the client class so a non-OpenAI provider gets
an honest no-op instead of a silently-ignored attribute. It shares the
process-wide `httpx.AsyncClient` by reference (pinned by a test) — no pool per
turn.

### 14.3 Level 4 can only narrow, never widen — and that is now explicit

§3 says all four levels must be true, and §5.3 says level 2 off means reasoning
never happens "whatever levels 3 and 4 say". Both hold. What the RFC does not
say, and what falls out of the mechanism, is that **level 4 cannot turn reasoning
ON where ops shipped no `reasoning_effort`.**

By the time the capability runs, the client already reflects levels 1-2. Turning
reasoning on therefore means "keep the effort ops configured"; there is no effort
value to apply when the profile declared `supports_thinking: true` without one
(legal per §4.3). Inventing one would be an ops decision, and §4.2 option B (a
`ThinkingSpec` carrying the effort) is the shape that would lift this — deferred
here on purpose.

The user-visible behaviour is coherent: the composer toggle decides whether the
reasoning ops and the platform admin already sanctioned applies to this question.
Practically, a deployment wanting a per-question toggle must give the profile a
`reasoning_effort` — which is also what makes the toggle's ON state meaningful.

### 14.4 §9 precondition 1 is broader than "reasoning-capable agents"

§9 asks for `max_tool_calls_per_turn` on "reasoning-capable agent configs". With
levels 3-4 shipped, any ReAct agent can select the `reasoning` capability, so
"reasoning-capable" is no longer a static property of an agent definition.

**As built:** the cap applies to all five ReAct agents in `apps/fred-agents`
(`tool_pacing.py`, 12 calls/turn), on every turn rather than only reasoning ones.
That is a behaviour change for non-reasoning turns and is deliberate — a runaway
tool loop is worth capping whatever caused it, `exit_behavior="continue"` means
hitting the cap degrades the answer rather than erroring the turn, and 12 is well
above the 1-4 a real turn uses. A capability-scoped alternative was rejected: a
capability-contributed `ToolCallLimitMiddleware` lands in the capability slot,
which sits *before* the HITL gate in the frame list and therefore *after* it in
`after_model`'s reverse order — the human gate would be asked about calls the cap
should already have blocked, breaking the ordering `frame.py` documents.

### 14.5 Level 3 needed an enforcement point, and the first cut had none

**Bug found in use, 2026-07-30.** An agent whose author had left reasoning off
reasoned anyway.

The RFC says all four levels must hold (§3) but never says *where* each is
enforced, and levels 3-4 were originally a capability, where "the capability is
not selected" implied "no middleware, no toggle, nothing runs". Amendment A
removed the capability without replacing that implication. What shipped gated
only the **composer control** on `tuning.reasoning_enabled`: with the agent's
switch off no toggle appeared, `RuntimeContext.reasoning` stayed `None`, and
`build_for_chat` — which strips only when the platform ceiling is closed or the
user actively declined — kept `reasoning_effort`. Level 3 was decoration.
Invisible by construction: the only UI that would have shown it is the toggle
that was correctly hidden.

**As built:** the ceiling handed to `build_for_chat` is `level 2 AND level 3`,
intersected in `_iterate_runtime_event_payloads` (`agent_app.py`) where the
`RuntimeContext` is assembled:

```python
reasoning_enabled_model_ids=(
    ctx.get("reasoning_enabled_model_ids")
    if tuning is not None and tuning.reasoning_enabled
    else []
),
```

Two properties worth keeping if this code moves:

- **it is pod-side, on `tuning`, not on `ctx`.** The model-ids list rides the
  request; `tuning` is resolved server-side from the managed instance. A client
  cannot open a gate its agent's author left shut — which is what "all four
  levels" has to mean to be worth anything.
- **`build_for_chat` stays the single strip point.** This computes a ceiling, it
  does not strip settings. Levels 1-4 still converge on one place.

Absent tuning (agent-to-agent invocation, no managed instance) means no author
ever enabled reasoning, so the ceiling is empty — the same fail-closed default as
everywhere else in this feature.

---

## 15. Amendment A — reasoning is not a capability (2026-07-30)

**Decided by the developer, after levels 3-4 were built as §7 specified and
seen in the product. Supersedes §7.1, §7.2 and §7.3.**

### The objection

> *"Ça n'a aucun sens d'activer le raisonnement au niveau du modèle et au niveau
> des outils."*

An agent author configuring reasoning found it in the **Tools** tab, next to
document access and MCP servers. That is the wrong mental model, and the RFC
walked into it: §7.1 observed that "chat controls are contributed **only** by
capabilities" and treated that as a constraint to satisfy rather than a gap to
close. Everything downstream followed from that one inference — the capability,
its `ConfigModel`, its `TurnOptionsModel`, the ReAct-only restriction, the
middleware, the `.bind`-vs-`model_copy` probe.

But an agent does not *use* reasoning the way it uses a tool. Reasoning is a
property of **how the model is called** — the same kind of thing as the search
policy or the RAG scope, both of which are platform chat options on
`RuntimeContext` and have never been capabilities.

### What replaces it

| Level | Was (withdrawn) | Is |
| ----- | --------------- | -- |
| 3 — agent offers it | `ReasoningCapability.ConfigModel.reasoning_enabled`, ticked in the Tools tab | `AgentTuning.reasoning_enabled`, a plain agent property (displayed in the Capabilities tab since §17, Amendment C) |
| 4 — user chooses per question | `TurnOptionsModel.reasoning`, via `turn_options[capability_id]` | `RuntimeContext.reasoning`, a platform chat option like `search_policy` |
| Composer control | `chat_controls()` on the capability | `_platform_reasoning_control` — control-plane emits the descriptor directly |
| Enforcement | a capability `awrap_model_call` patching the built client | the SAME `build_for_chat` point as level 2 |

**Two things got simpler, and that is the tell that this shape is right:**

1. **One enforcement point instead of two.** Level 4 is now applied where levels
   1-2 already were — on `ModelConfiguration.settings` before the client exists.
   The client-side `without_reasoning_on_client`, the `model_copy` mechanism, and
   the §12 q2 `.bind` probe that drove the choice between them are all gone, as
   is the risk of the two points drifting apart. §14.2 is now history rather than
   a live constraint.
2. **The ReAct-only restriction disappears.** §7.1 accepted losing levels 3-4 on
   Graph agents because a `middleware()`-only capability is refused at pod boot.
   With no capability and no middleware, that rule no longer applies: a Graph
   agent's model call goes through the same factory, so it gets levels 3-4 too.
   The exclusion was an artefact of the mechanism, never a product decision.

`RuntimeContext.reasoning` is deliberately **tri-state**: `None` means the agent
never offered the choice (levels 1-2 decide alone, the pre-REASON-01 behaviour),
`False` means the user actively declined, `True` means they asked. Collapsing
`None` and `False` would silently suppress reasoning on every agent that does not
opt in.

### The one thing this costs

Chat controls now have a second source. Before this, every descriptor came from
a capability (`AGENT-CAPABILITY-RFC.md` §3.3); now the platform can emit one, with
the reserved owner id `PLATFORM_CHAT_CONTROL_OWNER = "platform"`. The frontend
needed no change to accept it — its registry already falls back to the stock kit
by widget id when no plugin claims the `(capability_id, widget)` pair — but the
capability RFC's "only capabilities contribute chat controls" statement is now
false, and this is the amendment that says so.

---

## 16. Amendment B — the author decides where the composer's switch starts (2026-07-30)

**Status:** Implemented (2026-07-30). **Tracking:** GitHub #2175.

### The gap

Levels 3-4 as shipped give an author one binary: *offer* the toggle or not. The
value the toggle **starts at** was hardcoded — `params={"default": False}` in
`_platform_reasoning_control`. For an agent whose whole point is deliberation
(an analyst, a reviewer), that means every user must find and flip the switch on
every new conversation, and most never will: the feature is offered and unused.

The seam already existed and was one literal wide. `useComposerSettings` seeds
`ComposerState.reasoning` from the descriptor's `params.default` like any other
stock control (`§7.4`), so making that literal author-settable needs no new
channel, no new event, and no runtime change.

### What is added

One field, `reasoning_default_on`, on the same three surfaces as
`reasoning_enabled` (`ManagedAgentTuning`, the create/update requests, the
instance summary), rendered as a **second switch nested under the first** and
shown only while the offer is on — originally an indented row in the agent
form's General section, now (§17, Amendment C) inside the reasoning card's own
sub-form area in the Capabilities tab.

| | `reasoning_enabled` (level 3) | `reasoning_default_on` (Amendment B) |
| --- | --- | --- |
| Question it answers | is there a toggle? | where does that toggle start? |
| Gate or seed | gate — decides whether a control is emitted | seed — decides `params.default`, nothing else |
| Default | `False` | `False` (the previous hardcoded value) |

### Two properties this must keep, and the tests that pin them

1. **A preselection can never conjure a control.** §8's gates are evaluated
   first and unchanged: offer off, or no model reasoning platform-wide, still
   means *no descriptor at all*, whatever the default says. The failure this
   forecloses is an author leaving the default on, withdrawing the offer, and
   reasoning quietly staying on for users.
2. **The two fields never write each other.** Withdrawing the offer leaves the
   stored default alone — inert, since no control is emitted — so an author who
   toggles the offer off and back on recovers their choice instead of silently
   reverting to off. The frontend submits both fields unconditionally for the
   same reason.

Neither property is enforceable by the type system, so both are covered in
`tests/test_model_reasoning_toggle.py` and `AgentFormModal.test.ts`.

### Why this does not reopen §9

§9's mitigation is **level 2**, the platform-admin per-model off switch, and it
is untouched: an incident is still stopped in one click without touching any
agent. What Amendment B changes is the *exposure* an author can opt into — an
agent that starts reasoning on will hit `AGENT-THINKING-API-RFC.md` Amendment C's
measured duplicate-tool-call behaviour more often than one that starts off, and
on a tool-looping agent that is the risk §9 recorded.

Two things make that acceptable rather than a silent regression: the default
stays `False`, so nothing changes for any existing or future agent whose author
does not act; and the form's hint states the cost (slower, may repeat tool calls
on tool-using agents) at the point of decision, so the opt-in is informed. §9's
three preconditions shipped with phase 2 and are not weakened here.

### Level 4 is unchanged

`RuntimeContext.reasoning` stays tri-state and still carries the user's actual
per-question choice. A preselected `True` reaches the runtime as a user `True` —
correctly, because the user did send it and can flip it off before sending. What
an author sets is the composer's starting position, never a per-turn override
and never a ceiling; the ceiling remains levels 1-2 ∩ level 3 (§14.3, §14.5).

---

## 17. Amendment C — the toggle moves into the (renamed) Capabilities tab (2026-08-02)

**Decided by the developer. A frontend-only reversal of §15's tab-placement
argument — §15's backend conclusion (reasoning is not a capability: no
`ConfigModel`, no `TurnOptionsModel`, no middleware, one enforcement point at
`build_for_chat`) is untouched.**

### What changed

§15 moved the toggle out of the Tools tab because sitting "next to document
access and MCP servers" implied reasoning was one more tool an agent uses.
Since then the tab itself was renamed **Tools → Capabilities** (broader than
"tool use" — it's now the agent's list of extra things it can do, of which
document access and MCP servers are two examples). With the tab no longer
named after "tools", the objection §15 recorded no longer applies verbatim,
and the developer asked for the toggle to move back — visually — into that
tab, rendered with the same card component every real capability uses.

`CapabilityCard` (`AgentFormModal/CapabilityCard/CapabilityCard.tsx`) was
generalized rather than given a reasoning-specific sibling: it now takes a
plain `name`/`description`/`checked`/`onToggle` plus an optional `subForm`
slot, so `AgentFormBody.tsx` can pass the reasoning offer's own translated
strings and a `SwitchRow` (for the nested default-on toggle) as that slot,
exactly the way it passes a template capability's translated `name`/
`description` and a `CapabilityConfigForm` for its `config_fields`. One card
component for the whole tab, not reasoning's own copy of it.

### What did not change

`AgentTuning.reasoning_enabled` / `ManagedAgentTuning.reasoning_enabled`
remain plain agent properties, submitted and enforced exactly as §15/§16
describe — this is a relocation of the form control, not a reversion to the
§7 capability design. No `ConfigModel`, no `TurnOptionsModel`, no middleware,
no ReAct-only restriction; enforcement stays the single `build_for_chat`
point. `reasoning_default_on` (Amendment B) still nests under the offer, now
inside `CapabilityCard`'s `subForm` area instead of an indented row in the
General section.

### Where it lives now

| | Before (§15/§16) | Now (Amendment C) |
| --- | --- | --- |
| Tab | General section, under name/role/description | Capabilities tab, alongside the template's own capability cards |
| Component | Two indented switch rows in `AgentFormBody.tsx` | The same `CapabilityCard` every real capability renders through, `name`/`description`/`subForm` supplied by `AgentFormBody.tsx`; `SwitchRow` for the nested default-on toggle |
| Capabilities tab visibility | Hidden when the template advertises none | Always shown — the reasoning card no longer depends on `capabilities.length > 0` |
