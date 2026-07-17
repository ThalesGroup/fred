# RFC - Governed agent catalog admission

**Status:** Partially implemented (2026-07-17, CAPAB-01) — see §7.5. §6/§7.1-7.4
describe the originally proposed YAML-admission-catalog mechanism; §7.5
documents what actually shipped, which supersedes the catalog/status/
availability model in §6 with a capability-based one while keeping this RFC's
decision (§1) and enforcement points (§7.1, §7.2) intact.
**Author:** Dimitri Tombroff
**Date:** 2026-07-04
**Area:** control-plane, fred-runtime, frontend, deployment configuration
**Follows:** `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md`
**Touches:** `CONTROL-PLANE-PRODUCT-CONTRACT.md` (`/teams/{id}/agent-templates`,
agent enrollment), `RUNTIME-EXECUTION-CONTRACT.md` (direct runtime-agent execution
boundary)

---

## 1. Decision

Agentic pods may advertise agent templates, but advertised templates are **not
automatically deployable**.

Fred's target rule is:

> **The pod declares what exists. The control plane decides what is deployable.**

A runtime source being enabled means Fred can talk to the pod. It does **not** mean
every agent in that pod appears in the "Create agent" UI. A template appears only when
the platform has admitted it and the requested scope is allowed.

This RFC replaces the narrow "hide internal agents" framing with a governed catalog
model suitable for a shared Fred platform where several teams deploy their own agentic
pods.

## 2. Problem

Fred will host a shared platform where:

- the Fred team provides `fred-agents` as a reference pod;
- other teams can build and deploy their own agentic pods;
- the platform may connect several pods to one shared Fred instance;
- agent templates may use different tools, data paths, models, and operational
  assumptions.

Without central catalog governance, connecting a pod can accidentally make all of its
templates visible and enrollable for every team. That is not acceptable:

- a newly deployed pod may contain experimental or internal agents;
- an agent may be approved for one team but not another;
- an agent may be approved for team spaces but not personal spaces;
- an agent may need an offline security/business review before use;
- a template can be guessed by id even if the UI does not show it, unless enrollment
  checks the same policy server-side.

The existing `AgentDefinition.public` flag remains useful, but it is pod-local metadata.
It cannot express platform approval, team allowlists, personal-space publication, expiry,
or review provenance.

## 3. Scope

This RFC governs **template deployability**: whether a user can instantiate a managed
agent from a runtime template.

It does not define:

- how pods are packaged or deployed;
- how agent code is reviewed internally by the authoring team;
- model-provider approval;
- detailed tool-risk classification;
- break-glass access;
- prompt safety review workflow.

Those can feed the admission decision, but the decision outcome is the catalog policy
defined here.

## 4. Terms

**Runtime source / agentic pod**

A configured source in `runtime_catalog_sources`, identified by `runtime_id`.

**Template**

One agent definition advertised by a runtime pod, identified by `agent_id`.

**Template identity**

The stable composite identity:

```text
template_id = "{runtime_id}:{agent_id}"
```

**Admission**

The platform decision that a template is approved for use under defined scopes.

**Availability**

The scopes where an admitted template may be instantiated: selected teams, all teams,
selected personal spaces, or all personal spaces.

**Enrollment**

Creation of a managed agent instance from an admitted template.

## 5. Governance Roles

This RFC assumes the target role model from `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md`.

### PlatformAdmin

Owns platform admission:

- connect or disable runtime sources;
- admit or reject templates;
- set platform-wide constraints;
- publish a template to all personal spaces when justified;
- disable a template globally;
- review provenance, expiry, and audit status.

PlatformAdmin does **not** gain team data visibility from this role.

### TeamAdmin

Owns team adoption inside platform constraints:

- request availability for their team;
- approve use of an already platform-admitted template in their team;
- create or delegate creation of managed instances for their team;
- remove team availability when the team no longer wants the template.

### TeamEditor

May instantiate or configure agents only when TeamAdmin/platform policy delegates that
capability. TeamEditor is not the platform admission authority.

### TeamMember

Uses enrolled agents. TeamMember does not approve templates.

## 6. Target Policy Model

The control plane owns a configuration-backed admission policy.

Default posture:

```text
unknown runtime source  -> unavailable
unknown template        -> unavailable
new template            -> unavailable
```

An explicit admission entry is required before a template appears in a create-agent
catalog or can be enrolled by id.

### 6.1 Minimal Configuration Shape

The policy should be expressible as deployment configuration.

```yaml
agent_catalog_admission:
  defaults:
    unknown_templates: hidden
    require_explicit_admission: true

  templates:
    - runtime_id: "agentic-pod-xxx"
      agent_id: "agent-zzz"
      status: approved

      availability:
        teams:
          mode: allowlist
          ids:
            - "team-a"
            - "team-b"
        personal:
          mode: disabled

      decision:
        owner: "team-or-platform-owner"
        approved_by: "platform-admin-or-review-board"
        reviewed_at: "2026-07-04"
        ticket: "CVSSI-1234"
        expires_at: "2026-12-31"
        rationale: "Approved for team A/B after offline review."

      risk:
        level: medium
        notes:
          - "Uses team corpus search."
          - "No external write tools."
```

This file is an example shape, not a frozen schema. The required invariant is that the
decision is explicit, scoped, reviewable, and enforced by the control plane.

### 6.2 Status Values

Recommended status values:

| Status | Meaning |
| ------ | ------- |
| `approved` | Template may be listed/enrolled in the configured scopes. |
| `hidden` | Template is known but not visible or enrollable. Existing instances keep running unless separately disabled. |
| `deprecated` | New enrollment is blocked or warned; existing instances may continue. |
| `disabled` | New enrollment is blocked and existing execution may be blocked according to incident policy. |

`approved` is the only status that makes a template newly deployable.

### 6.3 Availability Values

For team spaces:

```yaml
teams:
  mode: disabled | allowlist | all
  ids: [...]
```

For personal spaces:

```yaml
personal:
  mode: disabled | allowlist | all
  user_ids: [...]
```

`personal.mode: all` is a platform-wide publication decision and should require a
stronger review than a team allowlist.

## 7. Enforcement Rules

### 7.1 Listing

`GET /teams/{team_id}/agent-templates` returns only templates that are:

1. advertised by an enabled runtime source;
2. locally visible from the pod perspective (`public=True`, unless the caller is using a
   dedicated internal/admin path);
3. admitted by control-plane policy;
4. available to the requested team or personal scope;
5. compatible with the caller's team capability.

The frontend must not implement additional visibility rules beyond displaying the
server-filtered result.

### 7.2 Enrollment

Enrollment re-checks the same admission policy server-side.

A user who guesses `runtime_id:agent_id` must not bypass catalog filtering. If the
template is not admitted for the target scope, enrollment returns 404 or 403 according to
the existing product convention; it must not create an instance.

### 7.3 Existing Instances

Policy changes must distinguish new enrollment from existing execution.

- `hidden`: blocks listing/enrollment; existing instances continue.
- `deprecated`: blocks or warns on new enrollment; existing instances continue.
- `disabled`: can block execution of existing instances, but this is an operational
  safety decision and should be audited.

This avoids surprising teams when a catalog decision changes.

### 7.4 Direct Runtime-Agent Execution

The product path is managed enrollment through the control plane. Direct bare
`runtime_id + agent_id` execution must not become a bypass around catalog admission.

Target rule:

- direct runtime-agent execution is either disabled for shared governed deployments, or
  the control plane checks the same admission policy before preparing such execution;
- runtime pods should not be externally reachable in a way that lets users bypass the
  control plane;
- if a runtime endpoint remains reachable for operational reasons, it is not a product
  deployability boundary and must not be used by the UI to create/use governed agents.

### 7.5 As implemented (2026-07-17, CAPAB-01 — supersedes §6's catalog model)

The shipped mechanism realizes this RFC's decision (§1: "the pod declares what
exists, the control plane decides what is deployable") and §7.1's listing
rules (specifically bullet 5, "compatible with the caller's team capability")
through the SAME ReBAC mechanism `AGENT-CAPABILITY-RFC.md` §8.1 already built
for tool capabilities (`#1988`), rather than the standalone YAML admission
catalog originally proposed in §6.1 (`status` + `availability.teams/personal`
config shape). An earlier draft of this implementation proposed a brand new
FGA `type template` mirroring `capability`'s relations — rejected on review as
exactly the duplication `#1988` already fixed once for MCP servers: two FGA
types, two enablement APIs, two seeding paths, mechanically identical.

- **Agent templates are capabilities, of a different `kind`, not a different
  type.** `CapabilityManifest`/`CapabilityCatalogEntry`
  (`fred_sdk/contracts/capability/manifest.py`) gained `kind: Literal["tool",
  "agent"] = "tool"`. No new FGA type, no new `Resource`, no new enablement
  API — the existing `capability` FGA type (`can_use`, `enabled`/`disabled`/
  `default_on`, `capabilities/enablement.py`) governs both.
- **Projection, not SDK type unification** — same precedent as `#1988`
  (`MCPServerConfiguration` was never made a `CapabilityManifest` subclass).
  `AgentDefinition` stays its own pod-registration type; control-plane
  projects each registered template into a `kind="agent"`
  `CapabilityCatalogEntry` (`product/service.py`
  `_agent_capabilities_for_source`), entirely control-plane side. This is
  deliberately NOT done by adding agent entries to the runtime pod's own
  `capability_registry` — that registry is what every template's
  `available_capabilities` (the Create-Agent-modal tool picker) is built
  from, reused identically across every template
  (`fred_runtime/app/agent_app.py` `list_agent_templates`); doing so would
  make every OTHER template's tool picker offer every agent as a selectable
  "capability" — an accidental side effect, not the deliberate
  `context.invoke_agent()` agent-as-sub-tool composition (a separate,
  unstarted idea).
- **Colon-free FGA id.** `template_id` (`f"{runtime_id}:{agent_id}"`, used for
  routing) contains `:`, forbidden by OpenFGA object ids — the same crash
  class `#1988` fixed for `mcp:<id>`. `template_capability_id(runtime_id,
  agent_id) -> f"{runtime_id}__{agent_id}"` is the parallel, ReBAC-safe id,
  used only for `can_use` checks and the admin catalog.
- **§7.1 realized**: `list_agent_templates` gates the `AgentTemplateSummary`
  entry itself (not just its nested `available_capabilities`) on
  `can_use(team, template_capability_id)`, batched with the existing
  `usable_capability_ids` call. **§7.2 realized**: `enroll_agent_instance`
  re-checks the same `can_use`, 404 on denial (anti-guessing, matching the
  existing non-public-template convention) — defense in depth against a team
  guessing a `template_id`.
- **Platform policy (CAPAB-01, ratified 2026-07-17, see
  `AGENT-CAPABILITY-RFC.md` §8.3): this deployment never uses `team_scope:
  DEFAULT_ON`**, for tools or agents — every team's access to every agent is
  an explicit, auditable admin grant. This makes §6.2/§6.3's `status`/
  `availability` vocabulary moot (superseded by the tri-state
  enabled/disabled/inherited-on the capability model already has) and makes
  a compatibility migration mandatory, not optional (§11 of this RFC still
  applies, realized differently): `grant_existing_teams_served_templates`
  writes an explicit `enabled` tuple (never `default_on`) for every
  (existing team × currently-served template) pair, so no team loses access
  to an agent it already uses at rollout. Must run before/with the `can_use`
  gate going live; rehearse against a copy of real data first.
- **Admin UI**: one surface, not two — the existing `/admin/capabilities`
  page (`CapabilitiesPage.tsx`) gained a `kind` filter ("Tools" | "Agents")
  over the same dataset, mutations, and drawer, rather than a new
  `AgentTemplatesPage`/route/nav entry. A tool can be depended on by several
  agents, so admins need both views, not one merged list or two disconnected
  surfaces.
- **Deferred, not part of this pass**: `depends_on` (a capability declaring
  it needs others) and the resulting "refuse and tell the admin what's
  missing" UX when enabling an agent without its tool dependencies granted.
  §7.1's "compatible with the caller's team capability" is satisfied by the
  agent-level gate alone for now; the dependency-aware refuse-and-signal
  layer is a fast-follow.
- **Not resolved by this change**: which templates end up visible to which
  teams is still "everything, for everyone who already had it" post-
  migration — the actual curation ask (fewer, better-chosen default
  templates per team) is a manual admin decision via the new UI, made after
  this ships, not automated here.

## 8. Relationship to `AgentDefinition.public`

`AgentDefinition.public` remains useful but has a narrower meaning:

- `public=False`: the pod says this template is internal and should not be listed by
  normal catalog discovery.
- `public=True`: the pod says this template may be considered for listing.

`public=True` does **not** mean platform-approved.

The final decision is:

```text
runtime advertises template
+ pod-local public flag
+ control-plane admission policy
+ requested scope
+ caller capability
= visible/enrollable or not
```

## 9. Product Behavior

For a team:

1. Team opens "Create agent".
2. Control plane receives `team_id`.
3. Control plane aggregates templates from runtime sources.
4. Control plane applies admission policy.
5. Control plane returns only deployable templates for that team.
6. Team creates an instance from one of those templates.
7. Enrollment stores the source `template_id`, `source_runtime_id`, and
   `source_agent_id` as today.

For personal spaces:

1. User opens their personal create-agent catalog.
2. Control plane applies `personal` availability.
3. Only templates admitted for that personal scope appear.

## 10. Audit Requirements

Every admission decision should be traceable:

- runtime id;
- agent id;
- status;
- allowed scopes;
- decision owner;
- approval reference or ticket;
- review date;
- expiry date if applicable;
- last policy update actor;
- reason/rationale.

Every blocked enrollment should be diagnosable without leaking hidden catalog contents to
unauthorized users.

## 11. Compatibility

Existing behavior can be preserved during rollout by generating an initial admission
policy for the current reference pod.

Recommended compatibility posture:

- `fred-agents` known production templates may be pre-admitted for the same scopes they
  effectively have today;
- `public=False` templates remain hidden;
- new runtime sources and newly discovered templates are hidden by default;
- existing managed agent instances keep running even if their template is not newly
  enrollable;
- enrollment, not execution, is the first enforcement point for newly governed catalog
  policy.

No immediate database or OpenFGA migration is required for the pure configuration form.

## 12. Acceptance Criteria

- A newly connected runtime source does not make its templates visible by default.
- A newly discovered template from an existing source is not visible by default.
- The create-agent catalog is filtered by control-plane admission policy.
- Enrollment re-checks admission and cannot be bypassed by guessing `template_id`.
- Team availability and personal availability are separate decisions.
- `personal: all` requires explicit platform admission.
- Existing instances are not silently removed by a visibility change.
- Direct runtime-agent execution does not bypass admission in governed deployments.
- `AgentDefinition.public` remains pod-local metadata, not platform approval.

## 13. Alternatives Considered

### Runtime-owned allowlists

Rejected. Each pod would become its own policy authority, and the shared platform would
not have a single reviewable source of truth.

### Frontend-only filtering

Rejected. It hides options visually but does not prevent enrollment by id.

### `public=True` means approved

Rejected. Pod authors can declare template visibility, but only the platform can approve
deployment on a shared Fred instance.

### Automatic availability to all teams after pod registration

Rejected. It is convenient but fails the governance requirement.

## 14. Summary

The target model is deliberately simple:

1. Agentic pods advertise templates.
2. Fred control plane admits templates.
3. Admission is explicit, scoped, configured, and auditable.
4. Team availability and personal availability are separate decisions.
5. Enrollment and listing enforce the same policy.

This makes Fred a governed agentic platform rather than a passive aggregator of every
agent template exposed by every connected pod.
