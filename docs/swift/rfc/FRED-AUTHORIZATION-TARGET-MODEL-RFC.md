# RFC - Fred authorization target model: Keycloak for SSO, Fred for authorization

**Status:** Proposed (Part 5 + Part 6 addenda implemented on branch, pushed through 2026-07-10 —
branch `1912-authz-05-fred-owned-authorization-model-keycloak-sso-only-fredopenfga-authorization`,
PR #1957, still awaiting human review before merge). Code-complete except item `8b`
(`NOTES-AUTHZ05-REVIEW.md`) — the Keycloak-`groups`-claim-derived `team_member` fallback, which is
blocked on the real production data migration (`fredlab-authz-migrate-swift.py`) having run, not on
any open design question. **Part 7 (2026-07-12, `AUTHZ-06`) code-complete, awaiting the
validation campaign** — cumulative team roles (one user may hold
`team_admin`+`team_editor`+`team_analyst` simultaneously on the same team). **Part 8 (2026-07-13,
`AUTHZ-07`) proposed, not yet implemented** — replaces config-embedded Keycloak `sub` bootstrap
with a k8s-style secret-gated bootstrap endpoint, plus a single declarative platform-provisioning
operation likely built by generalizing `PLATFORM-IMPORT-RFC.md` rather than a new endpoint.
Current
design state: `docs/swift/platform/REBAC.md`. Outstanding follow-ups:
`NOTES-AUTHZ05-REVIEW.md`.
**Date:** 2026-07-04
**Task ID:** `AUTHZ-05` (Part 7: `AUTHZ-06`; Part 8: `AUTHZ-07`)
**Audience:** Product governance, CVSSI, platform owners, then implementers
**Related work:** `AUTHZ-01` (`RBAC-TO-REBAC-MIGRATION-RFC.md`), `platform/REBAC.md`

---

## Executive Decision

Fred's target authorization model is:

> **Keycloak authenticates. Fred authorizes.**

Keycloak remains the SSO/OIDC bridge: login, token signature, stable user subject
(`sub`), and service-account authentication. Keycloak roles and groups are no longer
the product authorization authority.

Fred, through OpenFGA/ReBAC, owns all authorization:

- platform administration;
- platform observation;
- team membership;
- team-scoped roles;
- corpus/content permissions;
- evaluation permissions;
- service-principal permissions.

The central security rule is:

> **A platform role never grants team data visibility.**

A platform administrator can operate Fred. They do not automatically read, browse,
export, evaluate, or inspect a team's corpus, conversations, prompts, agents, or
evaluation data. Any access to team data requires an explicit team-scoped Fred/OpenFGA
relation or a narrowly-scoped, audited service operation.

---

# Part 1 - Target Model for CVSSI and Product Governance

## 1. Problem Statement

Fred currently carries historical authorization vocabulary from several stages of the
platform:

- Keycloak app roles: `admin`, `editor`, `viewer`;
- team relations: `owner`, `manager`, `member`;
- resource relations: `owner`, `editor`, `viewer`;
- organization-level OpenFGA permissions such as `can_manage_platform`.

The result is hard to explain and easy to misuse:

- "admin" can mean platform operation, product administration, or unintended access to
  team-scoped data;
- "editor" can mean global application role or resource editing;
- "owner" can mean team governance, resource ownership, or legacy bootstrap authority;
- Keycloak and Fred both appear to carry authorization meaning.

This ambiguity is itself a security risk. Even when individual endpoints are fixed, the
model remains difficult to audit because a reviewer cannot easily answer:

1. Who can administer the platform?
2. Who can observe platform health?
3. Who can administer a team?
4. Who can add documents to the team's corpus?
5. Who can read conversations for evaluation?
6. Can a platform administrator see team content?

The target model answers these questions directly.

## 2. Security Principles

### 2.1 Separation of authentication and authorization

Keycloak proves identity. It does not decide product authorization.

Fred uses the stable Keycloak `sub` as the subject id:

```text
Keycloak JWT -> user:<sub>
Fred/OpenFGA -> can user:<sub> perform action X on object Y?
```

### 2.2 No platform-to-team visibility inheritance

Platform roles are operational roles, not tenant-data roles.

A platform administrator may:

- manage platform configuration;
- manage users from the platform perspective;
- run import/export and lifecycle operations where authorized;
- inspect platform-level health, metrics, and audit surfaces.

A platform administrator may not, by that role alone:

- read a team's corpus;
- read team conversations;
- run or inspect team evaluations;
- browse team prompts or agent configuration;
- export a team's content as data;
- become `team_editor` (or any other team role) on a team it does not already hold.

### 2.3 Team access is explicit and scoped

Team access is represented in Fred/OpenFGA by explicit team-scoped relations.

Being authenticated is not enough. Being a platform administrator is not enough.
Being listed in an external identity group is not the final authority in the target
model.

### 2.4 Authorization is capability-based at enforcement time

Endpoints should check capabilities, not raw role names.

For example:

- check `can_manage_team_governance`, not "is manager";
- check `can_update_resources`, not "is editor";
- check `can_run_evaluations`, not "is analyst";
- check `can_manage_platform`, not "is admin".

Roles are human-readable bundles. Capabilities are the enforcement contract.

### 2.5 Default deny and auditable exceptions

If a relation or capability is not present, the request is denied.

Break-glass or support access is not part of the default platform role. If it is ever
needed, it must be a separate, time-bounded, auditable mechanism with explicit approval.

## 3. Target Human Roles

### 3.1 Platform roles

#### PlatformAdmin

Purpose: operate and secure the Fred platform.

Can:

- administer Fred platform configuration;
- manage platform-level users and service identities;
- bootstrap and delegate authorization;
- run platform import/export, lifecycle, and maintenance operations;
- view platform-level audit and operational metadata.

Cannot by default:

- read team content;
- read team conversations;
- browse team corpora;
- manage team-specific business process;
- assign themselves team access without an explicit, auditable delegation flow.

#### PlatformObserver

Purpose: observe platform health and compliance posture without operational write power
and without tenant-data visibility.

Can:

- view platform health, metrics, logs, and audit summaries that do not reveal team
  content;
- verify configuration posture and operational status.

Cannot:

- modify platform configuration;
- manage users or teams;
- access team data.

### 3.2 Team roles

#### TeamAdmin

Purpose: accountable person for the team's use of Fred: process, compliance, retention,
evaluation governance, and team role delegation.

Can:

- manage team governance settings;
- manage team role assignment within the boundaries set by platform policy;
- configure retention/compliance settings exposed to the team;
- authorize or supervise evaluation campaigns;
- inspect governance dashboards for their team.

Cannot by default:

- bypass corpus permissions unrelated to governance;
- read arbitrary conversations unless a specific capability grants it;
- operate the platform outside their team.

#### TeamEditor

Purpose: curate the team's corpus and operational content.

Can:

- add, update, move, process, and remove team corpus resources;
- manage document metadata and corpus structure;
- prepare content used by agents.

Cannot by default:

- manage team roles;
- change governance/retention settings;
- read conversations for evaluation unless also granted analyst capability.

#### TeamAnalyst

Purpose: evaluate agents using controlled, team-scoped evaluation data.

Can:

- create and run evaluation campaigns;
- manage evaluation corpora;
- access the limited conversation slices required to build and validate evaluation
  datasets, under policy and audit.

Cannot by default:

- manage all corpus resources;
- change team governance settings;
- administer team membership;
- read arbitrary team data outside evaluation scope.

#### TeamMember

Purpose: normal user of team-managed Fred capabilities.

Can:

- use team-managed agents;
- read team resources exposed to members;
- manage their own personal workspace.

Cannot:

- manage corpus resources;
- administer team settings;
- run privileged evaluation workflows;
- access other users' conversations.

## 4. CVSSI Assurance Statement

The target model reduces privilege ambiguity by making three boundaries explicit:

1. **Identity boundary:** Keycloak authenticates a subject; it does not grant Fred
   product authorization.
2. **Platform/team boundary:** platform operation does not imply tenant-data access.
3. **Role/capability boundary:** human roles are translated into audited capabilities;
   endpoints enforce capabilities.

This is more auditable than the legacy model because the reviewer can trace every
allowed action to a Fred/OpenFGA relation and every denial to absence of a relation.

---

# Part 2 - Target Technical Design, Including Bootstrap

## 5. Source of Truth

| Concern | Target authority |
| ------- | ---------------- |
| Human login | Keycloak / corporate SSO |
| JWT signature, issuer, audience, expiry | Keycloak |
| Stable user id | Keycloak `sub` |
| Platform roles | Fred/OpenFGA |
| Team roles | Fred/OpenFGA |
| Team membership | Fred/OpenFGA |
| Resource permissions | Fred/OpenFGA |
| Evaluation permissions | Fred/OpenFGA |
| Service-principal authorization | Fred/OpenFGA plus service identity authentication |

Keycloak groups may remain during the compatibility period as legacy membership input.
They are not the target authority.

## 6. Target OpenFGA Vocabulary

Names below are conceptual; implementation can choose exact snake-case relation names.

### 6.1 Organization object

Singleton:

```text
organization:fred
```

Target relations:

```fga
type service

type organization
  relations
    define platform_admin: [user, service]
    define platform_observer: [user] or platform_admin

    define can_manage_platform: platform_admin
    define can_manage_authorization: platform_admin
    define can_bootstrap_authorization: platform_admin
    define can_observe_platform: platform_observer
    define can_read_platform_audit: platform_observer
```

Rules:

- `platform_admin` does not flow into any team relation.
- `platform_observer` does not flow into any team relation.
- Organization permissions target platform surfaces only.
- If implementation chooses not to add a dedicated `service` type in the first
  step, service identities may remain represented by technical user subjects; the
  authorization invariant is unchanged: service principals receive explicit
  OpenFGA relations, never implicit platform-admin power.

### 6.2 Team object

Target relations:

```fga
type team
  relations
    define organization: [organization]

    define team_admin: [user, team]
    define team_editor: [user, team]
    define team_analyst: [user, team]
    define team_member: [user, team] or team_admin or team_editor or team_analyst

    define can_read_team_profile: team_member
    define can_manage_team_governance: team_admin
    define can_manage_team_roles: team_admin
    define can_update_resources: team_editor
    define can_update_agents: team_admin
    define can_run_evaluations: team_analyst or team_admin
    define can_manage_evaluation_corpus: team_analyst or team_admin
    define can_read_conversations_for_evaluation: team_analyst
    define can_use_team_agents: team_member
```

Rules:

- Team roles are explicit.
- Platform roles are not team roles.
- Team roles are translated into capabilities.
- Endpoint enforcement uses capabilities.

### 6.3 Resource objects

Existing tag/document/resource relations continue to exist, but should use the team
capability names as their team-owned permission source.

Example target direction:

```fga
type tag
  relations
    define owner: [user, team]
    define editor: [user, team]
    define viewer: [user, team]
    define parent: [tag]

    define read: viewer or editor or owner or read from parent or team_member from owner
    define update: editor or owner or update from parent or can_update_resources from owner
    define delete: owner or delete from parent or can_update_resources from owner
```

The exact resource model can evolve independently as long as it respects the target
rule: team content access is team-scoped and explicit.

## 7. Authorization Flow

### 7.1 Human request

1. User authenticates through Keycloak.
2. Backend validates JWT issuer, audience, expiry, signature.
3. Backend extracts `sub`.
4. Backend asks OpenFGA whether `user:<sub>` has the required capability on the target
   object.
5. Backend allows or denies.

No Keycloak role is required to authorize the operation.

### 7.2 Service request

1. Service authenticates with a dedicated service identity.
2. Backend validates the service credential.
3. Backend maps the service identity to an OpenFGA subject.
4. Backend checks the service capability on the target object.
5. Backend logs the operation with service identity, target, reason, and result.

Service identities are not "admins by default". They receive only the relations needed
for their task.

## 8. Bootstrap Problem

If Keycloak no longer grants product roles, Fred must still answer:

> Who is allowed to create the first PlatformAdmin relation?

This cannot depend on the Fred UI, because the UI itself requires authorization. The
bootstrap mechanism must be explicit, auditable, and safe against accidental lockout.

## 9. Bootstrap Options

### Option A - Configuration-seeded platform admins (recommended default)

Deployment configuration lists the initial Keycloak `sub` values allowed to become
`platform_admin`.

Example:

```yaml
authorization:
  bootstrap:
    platform_admin_subjects:
      - "4f0c3a33-0000-0000-0000-000000000001"
    mode: "idempotent"
```

Startup or a bootstrap command writes:

```text
user:<sub> platform_admin organization:fred
```

Properties:

- deterministic;
- auditable;
- compatible with offline/on-prem deployment;
- no Keycloak role dependency;
- easy to review before deployment.

Required safeguards:

- log every created relation;
- fail closed if the configured subject does not exist or cannot be validated when
  validation is enabled;
- idempotent writes;
- clear command to inspect current platform admins;
- no automatic removal unless explicitly requested.

### Option B - Bootstrap CLI/job

An operator runs a controlled command:

```text
fred-authz bootstrap-platform-admin --subject <keycloak-sub>
```

Properties:

- excellent for controlled operations;
- no application startup side effect;
- can be wrapped by deployment tooling.

Required safeguards:

- command requires platform deployment credentials, not a normal user token;
- writes an audit event;
- prints the exact tuple written;
- refuses ambiguous user identifiers unless a `sub` is supplied.

### Option C - Temporary legacy bridge for first admin only

During migration, a user with legacy Keycloak `admin` may create the first Fred
`platform_admin`. Once at least one Fred `platform_admin` exists, this bridge is disabled.

Properties:

- convenient for existing deployments;
- useful as a migration accelerator.

Risk:

- keeps Keycloak roles meaningful for a short period;
- must not become permanent.

Required safeguards:

- controlled by explicit config;
- logs every use;
- refuses use after first platform admin exists;
- has a removal date.

### Rejected Option - First logged-in user becomes admin

Rejected. It is convenient but unsafe. It can grant platform control to the wrong
person in a production SSO environment.

## 10. Recommended Bootstrap Policy

Use Option A for normal deployments and Option B for controlled operations.

Allow Option C only as a migration bridge for existing Swift/Kea deployments, with an
explicit expiration date and audit logging.

Acceptance criteria:

- a fresh deployment can create at least one PlatformAdmin without Keycloak roles;
- no platform admin can read team data without team relation;
- all bootstrap grants are visible in audit logs;
- there is a documented recovery procedure for accidental loss of all PlatformAdmins.

## 11. Implementation Work Breakdown

This RFC is design-only. Implementation should be split into reviewable steps:

1. Add target OpenFGA relations/capabilities without removing legacy relations.
2. Add Fred-side platform admin bootstrap.
3. Add target team-role assignment APIs/UI.
4. Update endpoint checks to target capabilities where needed.
5. Add audit/reporting for legacy bridge use.
6. Run compatibility window.
7. Disable legacy bridge.
8. Remove legacy role interpretation after all environments are migrated.

---

# Part 3 - Compatibility Proposition

## 12. Compatibility Goal

The goal is to deploy the target model without forcing an immediate complex migration
of:

- Keycloak roles;
- Keycloak groups;
- existing OpenFGA tuples;
- existing teams;
- existing users.

Compatibility is achieved by interpretation and audit, not by pretending the old model
is still the target.

> The old model is retained as a bounded compatibility layer while teams are migrated
> to the new least-privilege Fred/OpenFGA role model.

## 13. Compatibility Window

Recommended default:

- **T0:** release target model in compatibility mode.
- **T0 to T0 + 90 days:** legacy bridge enabled in `audit` mode.
- **T0 + 90 to T0 + 180 days:** legacy bridge enabled only by explicit deployment
  exception.
- **After T0 + 180 days:** legacy bridge disabled by default.

The exact dates should be set by release governance. The RFC fixes the policy shape:
compatibility is temporary, visible, and measurable.

## 14. Compatibility Modes

### `legacy_bridge = off`

Only target Fred/OpenFGA roles and capabilities authorize target surfaces.

Use for:

- new deployments;
- CVSSI validation environments;
- teams already migrated.

### `legacy_bridge = audit`

Legacy roles may still satisfy selected capabilities, but every use emits an audit
event:

```text
legacy_role_bridge_used:
  subject: user:<sub>
  legacy_relation: owner|manager|member|admin|editor|viewer
  target_capability: can_xxx
  resource: team:<id>|organization:fred
  decision: allowed
  replacement_needed: true
```

Use for:

- first production rollout;
- identifying teams that still depend on old relations.

### `legacy_bridge = enforce`

Legacy roles no longer authorize target capabilities, but the system can still report
what would have happened under compatibility.

Use for:

- dry-run cutover;
- final readiness validation.

Naming note: if implementation prefers `audit`, `warn`, `disabled`, that is fine. The
important point is the three states: allow+log, deny+report, deny fully.

## 15. Legacy Mapping Policy

Do not silently convert all old roles into new truth.

Use legacy mappings only as a bridge and as migration suggestions.

### 15.1 Platform legacy roles

| Legacy input | Compatibility interpretation | Target action |
| ------------ | ---------------------------- | ------------- |
| Keycloak `admin` | May satisfy selected platform capabilities during bridge | Grant explicit `platform_admin` in Fred |
| Keycloak `viewer` | May satisfy selected platform observation capabilities during bridge | Grant explicit `platform_observer` in Fred |
| Keycloak `editor` | Deprecated; should not receive new platform power by default | Review manually; usually no target platform role |

No Keycloak role grants team data visibility in the target model.

### 15.2 Team legacy relations

| Legacy relation | Compatibility interpretation | Target action |
| --------------- | ---------------------------- | ------------- |
| team `owner` | Legacy governance authority | Review and grant `team_admin` if still valid |
| team `manager` | Ambiguous: may be content operator or governance delegate | Review; grant `team_admin` or `team_editor` explicitly |
| team `member` | Normal user | Grant `team_member` if still valid |

Do not infer `team_analyst` automatically. Analyst access includes controlled
conversation/evaluation visibility and must be explicit.

## 16. Compatibility Schema Pattern

During the compatibility window, the schema may include both target and legacy
relations.

Conceptual example:

```fga
type service

type organization
  relations
    # Target
    define platform_admin: [user, service]
    define platform_observer: [user] or platform_admin

    # Legacy, compatibility only
    define legacy_admin: [user]
    define legacy_viewer: [user]
    define legacy_editor: [user]

    # Target capabilities
    define can_manage_platform: platform_admin or legacy_admin
    define can_observe_platform: platform_observer or legacy_viewer or legacy_editor
```

For team roles:

```fga
type team
  relations
    # Target
    define team_admin: [user, team]
    define team_editor: [user, team]
    define team_analyst: [user, team]
    define team_member: [user, team] or team_admin or team_editor or team_analyst

    # Legacy, compatibility only
    define legacy_owner: [user, team]
    define legacy_manager: [user, team]
    define legacy_member: [user, team]

    # Compatibility bridge
    define can_manage_team_governance: team_admin or legacy_owner
    define can_update_resources: team_editor or legacy_manager
    define can_use_team_agents: team_member or legacy_member
```

Implementation may keep existing relation names (`owner`, `manager`, `member`) as the
legacy names to avoid tuple migration. The RFC requirement is that the target names and
the legacy bridge are documented separately.

## 17. Readiness Report

Before disabling the legacy bridge, Fred must provide a readiness report:

- teams with no `team_admin`;
- users still authorized only through legacy team relations;
- platform users still authorized only through Keycloak roles;
- evaluation users missing explicit `team_analyst`;
- target capability denials that would have been allowed by legacy bridge;
- last seen date of each legacy bridge use.

This report is the operational basis for working with existing teams.

## 18. Team Migration Procedure

For each existing team:

1. Export current legacy role state.
2. Generate suggested target assignments.
3. Review with the team owner/business contact.
4. Grant explicit target roles.
5. Run in `audit` mode and confirm no unexpected legacy bridge use remains.
6. Switch that team to target-only enforcement if per-team flagging is available.
7. Otherwise mark the team ready for platform-wide bridge removal.

Suggested initial mapping:

| Current state | Suggested target |
| ------------- | ---------------- |
| Active legacy owner accountable for process/compliance | `team_admin` |
| Active legacy manager curating corpus/content | `team_editor` |
| Active legacy manager responsible for compliance/process | `team_admin` |
| Active legacy member | `team_member` |
| User running evaluation campaigns | `team_analyst` |

The suggestion is not authorization truth until it is written as a target Fred/OpenFGA
relation.

## 19. Compatibility Acceptance Criteria

The compatibility rollout is acceptable only if:

- old deployments can start without Keycloak or OpenFGA tuple rewrites;
- new target roles can be granted and enforced immediately;
- every legacy bridge authorization is logged;
- PlatformAdmin does not inherit team visibility;
- TeamAnalyst is never inferred from a legacy role;
- the readiness report identifies all remaining legacy dependencies;
- there is a published bridge removal date;
- disabling the bridge is a configuration change, not a data migration.

## 20. Non-Goals

This RFC does not:

- remove Keycloak as SSO/OIDC provider;
- remove Keycloak user `sub` as identity join key;
- define password lifecycle;
- define corporate SSO integration;
- implement break-glass team data access;
- redesign document/tag/resource sharing in full detail;
- require immediate deletion of legacy tuples.

## 21. Decisions to Confirm Before Implementation

1. Compatibility window length: default 180 days, or project-specific date?
2. Bootstrap mechanism: Option A only, or Option A plus CLI?
3. Whether per-team bridge disablement is required, or only platform-wide flag.
4. Exact target relation names: `platform_admin` vs `PlatformAdmin` in UI/API labels.
5. Whether `team_admin` can grant `team_analyst`, or whether that requires a
   separate approval path.
6. Which audit sink is authoritative for legacy bridge events.

---

---

# Part 4 - Swift Production Launch Addendum (2026-07-09)

## 22. Context

Swift opens a production platform in two weeks, on top of an **existing** Keycloak
realm and **existing** OpenFGA store: real users, real Keycloak groups (teams), and
real Keycloak app-role/team-relation assignments already exist. This is not a fresh
realm and not a multi-team, long-tail migration — it is one controlled cutover for a
known, finite population. This addendum resolves the `§21` open decisions concretely
for that launch. It does not change the target model in Parts 1-3.

## 23. Current-state findings that shape this addendum

Confirmed by reading `libs/fred-core/fred_core/security/rebac/schema.fga` and
`rebac_engine.py` (not assumed from docs):

- **Team membership (`member`) is not a stored tuple.** It is computed per request
  from the Keycloak JWT `groups` claim (`groups_list_to_relations`). Cutover requires
  no membership data migration; this keeps working unchanged for `TeamMember`.
- **Platform role (`admin`/`editor`/`viewer`) is also computed per request** from the
  JWT realm-role claim (`user_role_to_organization_relation`), not stored. The
  existing-admin population is enumerable directly from Keycloak, not from OpenFGA.
- **Team `owner`/`manager` are the only real stored OpenFGA tuples** in the current
  model — a small, queryable, finite set. Translating them per `§18` is a bounded,
  one-time job, not a bulk migration.
- **Active escalation bug:** `schema.fga` defines
  `team.owner = [user] or admin from organization`, and `list_teams()`
  (`control_plane_backend/teams/service.py:200`) calls
  `ensure_team_organization_relations()` for every Keycloak group on every listing,
  persisting the organization-team tie. Net effect **in production today**: any
  Keycloak `admin` app-role holder is an implicit `owner` of every team. This
  contradicts both `REBAC.md`'s stated design rule and this RFC's central rule
  (`§2.2`). It must be closed as part of this launch, not treated as a legacy
  artifact to bridge — see `§24.2`.

## 24. Decisions resolved for this launch

### 24.1 Compatibility window (`§21.1`)

Short controlled cutover, not the general-migration default (`§13`):

- **T0:** deploy target relations/capabilities alongside legacy ones (additive schema
  change only; no legacy tuples removed).
- **T0 to T0+5-7 days:** `legacy_bridge = audit` against the real swift Keycloak/OpenFGA
  data. Generate the `§17` readiness report daily.
- **Before go-live:** review the readiness report with the team; translate the known
  `owner`/`manager` tuples and `admin`/`editor`/`viewer` role holders per `§15`/`§18`
  into explicit target relations.
- **At go-live:** `legacy_bridge = enforce`, platform-wide (not per-team — this is one
  fresh production instance, not a staged multi-team estate; per-team flagging is not
  needed).

### 24.2 Escalation fix (`§21` — new item, not in the original six)

`team.owner = [user] or admin from organization` is removed/replaced before go-live,
not kept under audit-and-remove-later. Rationale: "platform admin/observer cannot see
team data" is this launch's explicit acceptance criterion, so shipping with this line
intact would fail the launch's own goal on day one. Replacement: `team.owner` becomes
`[user]` only (or the target `team_admin` direct-assign relation); `platform_admin`
capabilities remain organization-scoped per `§6.1` and carry no team edge.

### 24.3 Bootstrap mechanism (`§21.2`)

Option A (config-seeded `platform_admin_subjects`), not Option B or C. The existing
Keycloak `admin` population for swift is already known and small, so the subjects can
be listed directly in deployment config — no legacy-bridge bootstrap accelerator
(Option C) is needed for a launch that already knows its admins.

### 24.4 Bridge scope (`§21.3`)

Platform-wide flag, not per-team. Per-team bridge flagging exists to let a large
existing estate migrate team-by-team; swift is one instance cutting over as a whole.

### 24.5 Target relation names (`§21.4`)

Use the RFC's names as-is in code, API, and UI: `platform_admin`, `platform_observer`,
`team_admin`, `team_editor`, `team_analyst`, `team_member`. No aliasing.

### 24.6 TeamAnalyst delegation (`§21.5`)

`team_admin` may grant `team_analyst` directly, consistent with `TeamAdmin` owning
team role delegation (`§3.2`). No separate platform-level approval step.

### 24.7 Implementation note (2026-07-09, revised): team-bootstrap exception tried and reverted

Implementing `§24.2` as a blanket removal of `admin from organization` broke a
separate, documented requirement: `docs/swift/platform/REBAC.md`'s "locked design
authority" states team creation and first-manager assignment belong to the platform
admin, and no code path exists to assign a team's first owner other than that
escalation (there is no `create_team` flow that special-cases it). A completely
unscoped removal would leave newly created teams with no way to ever get an owner.

**First attempt (2026-07-09, reverted the same day):** `can_administer_owners` and
`can_administer_managers` additionally accepted `platform_admin from organization`
(the new, explicit, bootstrapped relation) — not the legacy Keycloak-derived `admin`.

**Review finding on PR #1957 (P1, confirmed):** this was itself an escalation, just
through a different door. OpenFGA relations are stateless — there is no way to
express "grant this only if the team currently has no owner yet". The exception
therefore applied to **every** team, always, not only freshly-created ones with no
owner. Control-plane's `add_team_member`/`update_team_member`
(`teams/service.py`) check exactly `can_administer_owners`/`can_administer_managers`
before writing a requested role change — with no other gate — so a `platform_admin`
could call those ordinary membership endpoints to self-promote (or promote anyone)
to owner/manager of **any existing team**, at any time, and from there inherit full
team data access through `owner -> manager -> member` (conversations, resources,
agents). That is the exact escalation this RFC exists to close, reintroduced through
`can_administer_owners`/`can_administer_managers` instead of `team.owner` directly.

**Corrected state:** `can_administer_owners`, `can_administer_managers`,
`can_administer_members`, and `can_update_info` are all owner-only, with **no**
platform-level escalation of any kind. Verified against a live OpenFGA instance, not
just the compiled schema JSON
(`fred_core/tests/integration/test_rebac.py::test_platform_admin_and_observer_never_grant_team_access`,
`::test_team_hierarchy_and_permissions`,
`fred_core/tests/security/test_rebac_schema_authz05.py::test_team_role_administration_has_no_platform_escalation`).

**The underlying team-bootstrap problem is still real and still unsolved** — tracked
as its own backlog item (`AUTHZ-MIGRATION-BACKLOG.md` §AUTHZ-05), not blocking this
PR. The RFC's own bootstrap section (`§9`, Option B — an operator-run CLI writing the
tuple directly with deployment credentials, not a standing capability reachable
through normal request authorization) is the right shape for the fix: bootstrap must
be a narrow, audited, one-time operation, never a capability platform_admin can reach
through ordinary API calls.

### 24.8 Audit sink (`§21.6`)

No dedicated audit-log store exists in the codebase today (checked: no `AuditLog`
model, only KPI writers under `libs/fred-core/fred_core/kpi/`). Recommendation:
emit `legacy_role_bridge_used` events (`§14`) as structured log lines in the existing
application logger for the audit window, plus a queryable readiness-report endpoint
(new, small) that reads current OpenFGA tuples directly rather than relying on a log
store. A durable audit sink is a separate, larger decision (`OBSERV` domain) out of
scope for this two-week launch — flag as a follow-up, not a launch blocker.

## 25a. Second finding: organization-level content bypass (2026-07-09, deferred)

While implementing `§24.2`, a second and larger gap was found: `OrganizationPermission.CAN_READ_CONTENT` /
`CAN_PROCESS_CONTENT` (gated by the Keycloak `viewer`/`editor` app role, computed live, org-scoped) authorize
roughly 30 call sites across `knowledge-flow-backend` — ingestion, vector search, corpus manager, statistics,
scheduler, audio transcription, report controller. None of these are team-scoped. Net effect: any user holding
the global Keycloak `editor` role (not even `admin`) can read/process **any team's** content today, independent
of team membership. This contradicts the RFC's central rule (`§2.2`) more broadly than the `team.owner`
escalation, and is not fixed by `§24.2`.

This is **not fixed in the 2026-07-09 implementation pass**. Closing it correctly requires auditing each of the
~9 controllers and threading a team-scoped capability check (resolving the relevant `team_id` from the request)
into each, which is its own reviewable unit of work — not something to bundle into the launch-safety fix.
Tracked as a new backlog item; must be resolved before this RFC's acceptance criteria (`§19`, `§25`) can be
considered fully met for swift production.

A live-reproducing regression tripwire for this exact gap now exists in the companion
`fred-deployment-factory` repo: `validation/scenarios/test_content_scope_bypass.py`, marked
`xfail(strict=True)` — it fails loudly (turns the run red) the day this is fixed and someone forgets
to update the test, instead of silently staying green on a vulnerability nobody re-checked.

## 25. Launch acceptance criteria (in addition to `§19`)

- The `admin from organization -> team.owner` path is removed before go-live.
- Every existing Keycloak `admin`/`editor`/`viewer` holder and every existing stored
  `owner`/`manager` tuple has an explicit target-relation translation decision on
  record (translated, or deliberately left out) before `enforce` mode.
- The readiness report shows zero unexplained legacy-bridge use in the 24 hours
  before go-live.
- The organization-level content bypass (`§25a`) is resolved, or explicitly accepted
  as a known residual risk by the platform owner, before the CVSSI/pentest sign-off.

---

# Part 5 - Second Implementation Pass (2026-07-09)

## 26. Terminology correction: `team_admin`, not `team_manager`

Parts 1-4 as originally drafted used `team_manager` for the team-governance role. That
name is corrected to **`team_admin`** throughout this document (retroactively, so Parts
1-4 above already read `team_admin`). Reason: the companion migration tool,
`fred-deployment-factory/bin/fredlab-authz-migrate-swift.py`, already ships with
`--target-team-admin-relation` defaulting to `team_admin`, and the deployment rehearsal
maps legacy `owner` to that flag. Renaming the RFC/schema to match avoids a second,
divergent vocabulary between the two repos. Confirmed target names, no aliasing
(supersedes `§24.5`): `platform_admin`, `platform_observer`, `team_admin`,
`team_editor`, `team_analyst`, `team_member`.

## 27. §25a resolved: which of the 34 call sites are fixed, and why the rest are not

A full inventory of every `CAN_READ_CONTENT`/`CAN_PROCESS_CONTENT` call site (34 sites,
7 controllers — `§25a`'s "~9 controllers" overcounted; the prose there in fact names
exactly these 7 areas) was read in full before deciding a per-site disposition. Blanket
team-scoping every site is not the right fix: several sites operate on data that
genuinely has no single team owner. The disposition:

**Fixed — team-scoped via the existing `TagPermission`/`DocumentPermission` checks on
the concrete object, replacing the org-level `CAN_READ_CONTENT`/`CAN_PROCESS_CONTENT`
check** (same pattern already used correctly by sibling endpoints in the same files,
e.g. `scheduler_controller.py`'s `TagPermission.UPDATE` check, `ingestion_controller.py`'s
per-tag loop):

- `statistic/controller.py`: `list_datasets`, `set_dataset` (tag/team id on the request);
  the 15 sibling calls that operate on the in-memory dataset loaded by `set_dataset`
  (`head`, `describe`, `detect_outliers`, `correlations`, `plot_histogram`,
  `plot_scatter`, `train_model`, `evaluate_model`, `predict_row`, `save_model`,
  `list_models`, `load_model`, `test_distribution`, `detect_outliers_ml`, `run_pca`) now
  re-check the tag id authorized at `set_dataset` time, carried in the service session
  state, rather than trusting the initial gate indefinitely.
- `vector_search/vector_search_controller.py`: `similarity_search`,
  `get_visual_evidence_artifact`, `rerank`.
- `corpus_manager/corpus_manager_controller.py`: `build_toc`, `revectorize`, `purge`
  (tag/library scope already on the request payload).
- `scheduler/scheduler_controller.py`: `process_documents` (per-file tag, mirrors
  `ingestion_controller.py`'s existing per-tag loop pattern).

**Fixed via a small, additive contract change** (new required `team_id`/`tag_id` field
— this is the part that closes the two `xfail` regression tests in
`fred-deployment-factory/validation/scenarios/test_content_scope_bypass.py`):

- `corpus_manager/corpus_manager_controller.py`: `capabilities`, `tasks_get`,
  `tasks_result`, `tasks_list` — none of these carried a team-identifying value before;
  they now require a `team_id`/`tag_id` param and check `TeamPermission`/`TagPermission`
  on it.
- `content/report_controller.py` / `report_service.py`: report writes had **no team
  association in the data model at all** (`source_tag="reports"`, no `tag` parent
  relation ever created). `write_report` now requires a `tag_id` and creates the `tag`
  parent relation, so reports become team-owned content like everything else, and
  `TagPermission.UPDATE` gates the write.

**Left intentionally org-scoped — not a gap, documented as such in `schema.fga`**:
the remaining ~17 sites are genuinely resource-less utilities with no team-owned data
to protect: the 15 in-memory statistic calls are covered by the `set_dataset` re-check
above, not counted twice; audio transcription (stateless dictation), `fast_markdown`/
`fast_ingest` (stateless extraction / session-scoped chat attachments, not team-owned),
and the OpenAPI-typegen/dummy test routes (`echo_schema`, `test_post_success`). Making
these "team-scoped" would mean inventing a team owner for data that structurally has
none — left as `viewer`/`editor` org-level gates (any authenticated content-capable
user), with an inline comment in `rebac_engine.py` explaining why, so this doesn't read
as an oversight on the next audit.

## 28. Team-bootstrap problem resolved: platform-admin-gated create-team endpoint

`§24.7` left the team-bootstrap problem open (assigning a freshly created team's first
`team_admin`) and pointed at `§9` Option B (an operator CLI) as the right shape. Reading
`teams/service.py` in full during this pass found there is in fact **no team-creation
flow at all today** — a "team" is a Keycloak root group, discovered lazily by
`list_teams`/`_fetch_root_keycloak_groups`; `add_team_member` requires the group to
already exist. A freshly created Keycloak group is therefore unreachable by every
existing membership endpoint (all gated on already having `team_admin`) until this
pass — this was a real dead end, not merely a missing convenience.

Resolution: `Option B` is implemented as an API endpoint + minimal admin-console UI
instead of a bare CLI, since the platform already has an authenticated platform-admin
surface to place it in:

- Reuses the **existing** `can_create_team` capability (previously `admin` only, now
  `admin or platform_admin`, eventually `platform_admin`-only once the legacy bridge is
  disabled) — no new capability invented.
- `POST /teams { name, initial_team_admin_ids: [str, ...] }` (min 1 admin id — an
  adminless team cannot be created, mirroring the migration tool's own
  `--allow-zero-team-admin` guard).
- Creates the Keycloak root group, adds each named user to it, then writes explicit
  `team_admin` OpenFGA tuples for exactly those subjects. The calling `platform_admin`
  receives no relation on the new team unless they name themselves in the request —
  an explicit, visible, revocable self-grant, never an implicit one.
- **One-shot by construction, not by an unenforceable OpenFGA predicate:** because this
  is a *create* endpoint, it 409s if the team already exists. It cannot be replayed
  against an existing team to change its admins — that is exactly what made the
  reverted `§24.7` attempt unsafe (a standing grant reachable on every team, forever).
  All subsequent admin changes still go through the unchanged, `team_admin`-gated
  `add_team_member`/`update_team_member`/`remove_team_member` endpoints.
- Two-system consistency: Keycloak group creation and the OpenFGA tuple writes are not
  one transaction. On partial failure after group creation, the endpoint rolls back
  (deletes the just-created group) rather than leaving an orphaned adminless group.
- Logged as a structured audit line (who, team, initial admins), consistent with
  `§24.8`'s interim audit-sink approach.

**Superseded by Part 6 below (2026-07-10):** the "creates the Keycloak root group" step
described above is corrected — teams stop being Keycloak groups at all. `§28`'s
capability gate (`can_create_team: platform_admin`) and safety properties (one-shot,
no standing relation for the calling platform_admin, rollback on partial failure) are
unchanged; only the storage mechanism changes, from a Keycloak group to a
`team_metadata` row.

---

# Part 6 - Team Registry Decoupled From Keycloak (2026-07-10)

## 29. Why this part exists

Implementing `§28`'s bootstrap endpoint surfaced a question CVSSI will ask directly:
if Keycloak is identity-only, why does creating a team still create a Keycloak group?
Reading `teams/service.py` in full during this pass confirmed the answer was "it
still doesn't fully apply yet" — `list_teams`, `create_team`, `get_team_by_id`,
`update_team`, `list_team_members`, `add_team_member`, `remove_team_member`, and
`update_team_member` all depend on the Keycloak Admin API today. This part corrects
that: a team is a `team_metadata` row plus its OpenFGA relations, full stop. Keycloak
manages user accounts (login, JWT, stable `sub`) and nothing about teams.

**Implemented 2026-07-10** (AUTHZ-05 review item 9, `NOTES-AUTHZ05-REVIEW.md`): every
function this section names was rewritten exactly as specified below, verified against
the full offline suite of all touched projects plus a live OpenFGA instance, and the
control-plane OpenAPI client was regenerated. Team `name` is immutable after creation
(confirmed with the developer — not decided silently, since `§31` left it open).

**Explicitly out of scope for this part**: translating *existing*, already-live
Keycloak-group-backed teams onto this model. That is a one-time operational backfill
(read each existing group's `id`/`name` once, write the equivalent `team_metadata` row)
to run separately, whenever this lands on an environment that already has real teams.
On a fresh deployment with zero pre-existing teams there is nothing to backfill — this
part can be implemented and used immediately with no migration step. (Developer
decision, 2026-07-10: do not conflate this with `§24`'s legacy-role migration; that
migration is a distinct, already-tracked concern.)

## 30. Data model change

`libs/fred-core/fred_core/teams/team_metatada_models.py` (`TeamMetadataRow`, table
`teammetadata`) gains a `name: Mapped[str] = mapped_column(String(180), nullable=False)`
column — via a new Alembic migration in `apps/control-plane-backend/alembic/versions/`,
following the exact pattern of the existing `e3f4a5b6c7d8_add_team_metadata_retention.py`
migration (same table, same kind of additive column). `TeamMetadata`/`TeamMetadataPatch`
(`libs/fred-core/fred_core/teams/metadata_store.py`) gain the corresponding `name`
field. `TeamMetadataStore` gains a `list_all() -> list[TeamMetadata]` method (a plain
`SELECT * FROM teammetadata`, no filter) — there is no such enumeration method today;
every existing read goes through `get_by_team_id(s)` keyed by already-known ids.

## 31. Service-layer rewrite (`apps/control-plane-backend/control_plane_backend/teams/service.py`)

Every function below currently calls the Keycloak Admin API (via
`deps.create_keycloak_admin_client()`); after this part, none of them do.

- **`create_team`**: generate `team_id` as a fresh `uuid4().hex` (no longer a Keycloak
  group id). Check name uniqueness against `team_metadata_store` (query by name; a
  Keycloak group's name-uniqueness constraint no longer does this for us) and raise
  `TeamAlreadyExistsError` on collision — this preserves the "one-shot by construction"
  property `§28` established. Write one `team_metadata` row (`id`, `name`). Write the
  `team_admin` tuple(s) for `initial_team_admin_ids`, exactly as today. On partial
  failure after the metadata row is written, delete that row (same rollback shape as
  today's Keycloak-group rollback, different target).
- **`list_teams`**: enumerate candidate team ids from `team_metadata_store.list_all()`
  instead of `_fetch_root_keycloak_groups`. Keep the existing `CAN_READ` filter
  (`rebac.lookup_user_resources`) unchanged — only the candidate-id source changes.
- **`list_all_teams_unfiltered`** (added in the AUTHZ-05 review pass, item 3): same
  change — source candidate ids from `team_metadata_store.list_all()` instead of
  Keycloak root groups. The safety property (only call this when the caller already
  passed `CAN_MANAGE_PLATFORM`) is unchanged.
- **`get_team_by_id` / `update_team` / `_validate_team_and_check_permission`**: team
  existence check becomes `team_metadata_store.get_by_team_id(team_id)` (raise
  `TeamNotFoundError` if `None`) instead of `admin.a_get_group(team_id)`. Name comes
  from the metadata row. Whether `name` becomes patchable through `update_team` (team
  rename) or stays immutable after creation is an open product question, not decided
  by this RFC — flag it for the developer rather than deciding silently.
- **`list_team_members`**: full member list via
  `rebac.lookup_subjects(team, RelationType.TEAM_MEMBER, Resource.USER)` (already
  covers `team_admin`/`team_editor`/`team_analyst` through the existing `team_member`
  union — no separate Keycloak group-member fetch needed). Role labeling per member
  reuses the existing `_get_team_users_by_relation` calls for `TEAM_ADMIN`/
  `TEAM_EDITOR`/`TEAM_ANALYST` (same pattern already in this file, just no longer
  paired with a Keycloak member fetch).
- **`add_team_member` / `remove_team_member` / `update_team_member`**: drop
  `_add_keycloak_user_to_group`/`_remove_keycloak_user_from_group` entirely — pure
  OpenFGA relation writes/deletes, which these functions already do alongside the
  Keycloak calls today.
- **Dead code to remove**: `_fetch_root_keycloak_groups`, `_fetch_group_member_ids`,
  `_add_keycloak_user_to_group`, `_remove_keycloak_user_from_group`,
  `_map_keycloak_membership_error`, the `KeycloakGroupSummary` type,
  `TeamMembershipSyncError`. Verify before removing `KeycloakM2MDisabledError` and
  `create_keycloak_admin_client` from `TeamServiceDependencies` — `KeycloakM2MDisabledError`
  may still be meaningful if any remaining function in this file needs the Keycloak
  admin client for a non-team-group reason; check call sites first, do not assume.

## 32. New platform-registry capabilities (team governance, not team data)

Distinct from `§2.2`'s central rule: these three capabilities let `platform_admin`
govern the *existence* of teams (the registry) — they grant nothing about a team's
agents, prompts, conversations, or resources, which remain governed exclusively by
team relations as everywhere else in this RFC.

```fga
type organization
  relations
    define can_list_all_teams: platform_admin
    define can_delete_team: platform_admin
    define can_rescue_team_admin: platform_admin
```

- **`can_list_all_teams`** → `GET /teams/all`. Returns `Team` objects (`id`, `name`,
  `admins`) for every team in `team_metadata_store`, regardless of the caller's own
  membership. Reuses `list_all_teams_unfiltered` (§30's rewritten version). Deliberately
  does not return `permissions` (the `TeamWithPermissions` shape) — nothing here should
  read as team-data access.
- **`can_delete_team`** → `DELETE /teams/{team_id}`. Deletes the `team_metadata` row and
  every OpenFGA relation referencing `team:<id>` via the existing
  `RebacEngine.delete_all_relations_of_reference` (already implemented, already used
  for user cleanup — no new ReBAC primitive needed). No Keycloak group to delete, since
  none exists after Part 6. Always logged (structured line, consistent with `§24.8`'s
  interim audit-sink approach — no durable audit store exists yet).
- **`can_rescue_team_admin`** → `POST /teams/{team_id}/rescue-admin { user_id }`. Writes
  a `team_admin` tuple for `user_id` **only if the team currently has zero `team_admin`**
  (checked via the existing `_get_team_users_by_relation(rebac, team_id,
  RelationType.TEAM_ADMIN)` — if non-empty, reject with a clear error naming the
  existing admin(s), instructing that they must handle it, not platform_admin). This
  guard is the load-bearing safety property and must not be relaxed or made optional:
  it is what makes this action structurally different from the `§24.7` escalation that
  was tried and reverted. That attempt failed because the exception applied to *every*
  team, always, reachable through the *ordinary* membership endpoints — indistinguishable
  from routine self-service. `can_rescue_team_admin` is a separate, narrowly-purposed
  endpoint that is mechanically inert against any team with an active admin, and can
  only ever act on a genuinely orphaned team. Do not generalize it into "platform_admin
  can reassign any team's admin at any time" — that is the exact shape of the rejected
  escalation, just renamed.

---

# Part 7 - Cumulative Team Roles (2026-07-12)

## 33. Why this part exists

`§26`'s "hard cross-write rule" (`REBAC.md`, `schema.fga` lines 61-67) made `team_admin`
and `team_editor` **orthogonal, not hierarchical**: `team_admin` has full governance
authority (membership, settings) and zero content authority (prompts, agents);
`team_editor` is the reverse. This is a genuine security property — it caps the blast
radius of one compromised account — but it was never actually mandated by this RFC's
own text. `§6.2`'s original target vocabulary (line 344) wrote
`define can_update_agents: team_admin` — i.e. the admin role originally *did* carry
content authority. The orthogonal split was introduced during implementation (item 7,
`NOTES-AUTHZ05-REVIEW.md`, 2026-07-09) without a dedicated RFC section arguing for it;
`§26` is a pure renaming section (`owner`→`team_admin`, `manager`→`team_editor`) and
says nothing about hierarchy.

The practical consequence, surfaced 2026-07-12 while validating the live stack
persona-by-persona: the product's own write path (`update_team_member`) enforces
**exactly one role per user per team** — it deletes every existing team relation for
that user before writing the requested one
(`teams/service.py::_remove_all_team_member_relations` then `_add_team_member_relation`).
Combined with the orthogonal split, this makes the common small-team shape —
one person who is simultaneously the team's governance authority, its content editor,
and its evaluation operator, plus a handful of plain members — structurally
unreachable. A solo `team_admin` cannot update a prompt or an agent in their own team.

## 34. Decision: additive roles, not a schema change

**OpenFGA already supports this. `schema.fga` needs zero changes.** Nothing in the
schema enforces exclusivity — `team_admin: [user]`, `team_editor: [user]`,
`team_analyst: [user]` are three independent relations; a user can already hold
multiple simultaneous tuples on the same `team:<id>` object today, at the ReBAC layer.
The exclusivity is a **service-layer convention** (`update_team_member`'s
remove-then-add-one), not a model constraint. `can_run_evaluations`/
`can_manage_evaluation_corpus` (`§6.2`) already union `team_analyst or team_admin` —
proof the schema was never actually opposed to a `team_admin` holding overlapping
capabilities.

**Decision:** a user may hold any combination of `team_admin`, `team_editor`,
`team_analyst` on the same team simultaneously, each granted and revoked as an
independent, explicit action — never a bulk "replace the role set" operation. This
preserves the RFC's constant theme (explicit relations, no implicit escalation) at
finer grain: granting `team_editor` to an existing `team_admin` requires
`can_administer_editors` exactly as it would for anyone else; nothing about already
holding `team_admin` implicitly grants or simplifies acquiring another role.

**Explicitly out of scope:** any cap on how many people may hold a given role on one
team, and any change to the orthogonal *capability* definitions themselves
(`can_update_resources`/`can_update_agents` stay `team_editor`-only;
`can_manage_team_governance`-equivalent capabilities stay `team_admin`-only). This part
only removes the **one-role-per-user** restriction — it does not touch which
capabilities each role carries, and does not reopen `§26`'s renaming or `§32`'s
registry-governance capabilities.

## 35. Service-layer changes (`teams/service.py`)

- `_get_user_role_in_team` (singular, priority-resolved `UserTeamRelation`) becomes
  `_get_user_roles_in_team` (`set[UserTeamRelation]`) — the priority-fallback logic is
  retired at the source of truth, kept only where a single "primary role" is still the
  right display (`§37`).
- `_remove_all_team_member_relations` is unchanged, still used for full member removal
  (`remove_team_member`). A new sibling, `_remove_team_member_relation` (one relation,
  mirrors the existing `_add_team_member_relation`), supports revoking a single role
  without touching the others.
- `update_team_member` ("replace the one role") is retired, replaced by two explicit
  functions — `grant_team_member_role` / `revoke_team_member_role` — each independently
  permission-checked via the existing, unchanged
  `_get_administer_permission_for_team_role_relation` (granting `team_admin` still
  requires `can_administer_admins`, etc. — this function does not change).
  `revoke_team_member_role` additionally refuses (`TeamMemberRoleNotHeldError`,
  `TeamMemberLastRoleError`) a revoke of a role not held, or a member's only remaining
  role.
- `_ensure_team_keeps_at_least_one_admin` generalizes from "role transition" to "would
  this revoke the team's last `team_admin`" — same invariant, checked on a single-role
  revocation instead of a from/to pair.
- `add_team_member` (first role granted when adding a brand-new member) is unaffected —
  a new member still starts with exactly one role; additional roles are granted
  afterward through the same granular action as for existing members.

## 36. Contract change (frozen — `CONTROL-PLANE-PRODUCT-CONTRACT.md`)

`TeamMember.relation: UserTeamRelation` (singular) becomes
`TeamMember.relations: list[UserTeamRelation]` (the full set the member currently
holds). Requires an OpenAPI regeneration and a dated entry in
`CONTROL-PLANE-PRODUCT-CONTRACT.md`, same discipline as `§14`'s `PermissionSummary`
change (item 11).

`PATCH /teams/{team_id}/members/{user_id}` ("set the one role") is retired — its
"replace" semantics no longer make sense once a member can hold several roles.
Replaced by two granular endpoints, implemented as their own routes rather than an
action-flag body param, so grant and revoke are distinguishable at the HTTP-method
level, not just by payload shape:

- `POST /teams/{team_id}/members/{user_id}/roles` (`GrantTeamMemberRoleRequest`,
  replaces `UpdateTeamMemberRequest`) — grants one additional role.
- `DELETE /teams/{team_id}/members/{user_id}/roles/{relation}` — revokes one role,
  refusing (`409`) a revoke that would leave the member with none (that is a removal,
  not a role change — use `DELETE /teams/{team_id}/members/{user_id}` instead).

`AddTeamMemberRequest` (`POST /teams/{team_id}/members`, first role for a brand-new
member) is unchanged.

## 37. Consumers audited, decision locked per consumer (2026-07-12, developer-confirmed)

- **`useTeamCapabilities`/`teamCapabilities.ts` (frontend, and everywhere in the app
  that gates a button/route on "can I do X on this team")**: reads
  `TeamWithPermissions.permissions` (`_get_team_permissions_for_user`), a resolved
  capability list already computed by unioning `has_permission` across every relation
  the caller holds. **Zero change** — this was already multi-role-safe by construction.
- **`import_export/stats.py`'s platform-wide per-team admin/editor/analyst/member
  counts**: stays a strict partition, one column per member, using the same
  priority-fallback (`admin` > `editor` > `analyst` > `member`) `_get_user_role_in_team`
  used to compute today, so the columns keep summing to `total_members` and the
  platform-data admin page's meaning does not change. The full, cumulative role set
  per member remains visible in the team's own member-management table (`§37` next
  bullet) — the platform-wide aggregate deliberately stays a simplified one-row-per-
  person view.
- **`TeamSettingsMembersTable.tsx` (team member management UI)**: the single-select
  role dropdown per row becomes a set of independently togglable roles (one control per
  `team_admin`/`team_editor`/`team_analyst`, each gated by its own
  `can_administer_{admins,editors,analysts}` exactly as today), plus the implicit
  `team_member` baseline. Roster sort order uses the highest-priority role held (same
  `ROLE_PRIORITY` table, applied to the max over the held set instead of a single
  value).
- **`cli/main.py`'s member-listing table**: cosmetic — the `relation` column becomes a
  joined list of held roles.

## 38. Non-goals (explicit, to prevent scope creep during implementation)

- No cap or warning on how many people hold a given role on one team.
- No change to `can_update_resources`/`can_update_agents`/`can_manage_team_governance`
  -equivalent capability definitions — the orthogonal *capability* split from `§26`
  stands; only the one-role-per-user restriction is lifted.
- No change to `§32`'s registry-governance capabilities
  (`can_list_all_teams`/`can_delete_team`/`can_rescue_team_admin`) or their guards.
- No bulk "set my roles to [...]" endpoint — grant/revoke stays one explicit role at a
  time, so every change remains individually permission-checked and logged.

## 39. Validation plan for this part

Full regression, not incremental: `make clean` / `make test` / `make code-quality` in
every touched project (`libs/fred-core`, `apps/control-plane-backend`,
`apps/frontend`), then `fred-deployment-factory`'s `make validation-report` against the
live stack, then a manual/self-test UI pass per persona — including two new
deployment-factory test profiles seeded with combined `team_admin`+`team_editor`+
`team_analyst` roles in `fredlab`, specifically to exercise this part. Results recorded
in `docs/swift/platform/authz-endpoint-matrix.yaml` (endpoint-level) and a new,
dedicated test-campaign registry (persona/scenario-level OK/KO), not only in
`NOTES-AUTHZ05-REVIEW.md` prose.

---

# Part 8 - Root Bootstrap and Platform Provisioning (2026-07-13)

## 40. Target

`§24.3`'s config-seeded `platform_admin_subjects` is superseded: declaring a Keycloak `sub` in
deployment config couples application config to an identity-provider implementation detail, and
is fragile across realm re-imports. Two problems, two mechanisms — no CRUD, no identity ever
stored in deployment config:

1. **Root bootstrap.** A fresh deployment has no `platform_admin` yet, and the UI/API cannot
   authorize its own bootstrap. Fred adopts the same shape every access-controlled system uses for
   this — Kubernetes' cluster-admin bootstrap via kubeconfig, ArgoCD's
   `argocd-initial-admin-secret`, Rancher's bootstrap password: deployment tooling generates a
   one-time secret out-of-band (a Kubernetes Secret for GKE/AKS; an equivalent generated file for
   the local dev stack), and a single endpoint resolves the intended admin's identity
   (email/username) at call time and grants `platform_admin` — permanently refusing once any
   `platform_admin` already exists (a live OpenFGA check, not a flag, same discipline as
   `can_rescue_team_admin`, `§32`). No Keycloak `sub` is ever declared in config.
2. **Platform provisioning.** Populating a fresh platform with teams, roles, and users is not a
   sequence of CRUD calls — it is one declarative operation: hand Fred a description of the target
   state, Fred reconciles it. This is not a new capability to invent: `PLATFORM-IMPORT-RFC.md`
   already does almost exactly this — a `platform_admin`-gated import that repopulates an empty
   instance's teams, users, and OpenFGA tuples from a bundle, refusing to run against a non-empty
   target (`§2`, "fresh target only"). The likely right move is to harden and generalize that
   mechanism's input contract (today scoped to a kea-snapshot bundle) rather than build a second,
   parallel bulk-provisioning endpoint — to be confirmed with whoever owns that RFC before any
   implementation.

## 41. Non-goals

No option catalogue, no CRUD-style team/role provisioning API, no identity ever declared in
deployment config or values files. `§9`'s bootstrap options and `§24.3`'s config-seeded-subjects
decision are superseded by this part for any deployment created after it lands.

---

## Summary

The target is intentionally simple:

1. Keycloak authenticates (identity, SSO, JWT — including for individual user accounts;
   never groups, never roles used for authorization).
2. Fred/OpenFGA authorizes everything: platform roles, team roles, team existence, team
   membership, resource permissions.
3. Platform roles do not grant team data access. The three narrow exceptions
   (`can_create_team`, `can_list_all_teams`, `can_delete_team`, `can_rescue_team_admin`)
   govern the team *registry*, never a team's content, and `can_rescue_team_admin` is
   structurally inert against any team that already has an admin.
4. Team roles are explicit, stored OpenFGA tuples — never derived from a Keycloak role
   or group.
5. No legacy bridge survives in the target state: `§24.2`/`§24.7`'s escalation and
   `§26-28`'s Keycloak-derived team relations are removed outright once the one-time
   translation of existing data is complete, not kept behind a permanent toggle
   (developer decision, 2026-07-09 — see the AUTHZ-05 review notes).

This gives CVSSI a stable, fully auditable model: every allowed action traces to an
explicit Fred/OpenFGA relation, and every team-registry action a platform_admin can
take is itself narrow, logged, and incapable of reaching into team data.
