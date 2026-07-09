# RFC - Fred authorization target model: Keycloak for SSO, Fred for authorization

**Status:** Proposed
**Date:** 2026-07-04
**Task ID:** `AUTHZ-05`
**Audience:** Product governance, CVSSI, platform owners, then implementers
**Related work:** `AUTHZ-01` (`RBAC-TO-REBAC-MIGRATION-RFC.md`), `KEYCLOAK-USER-TEAM-REMOVAL-RFC.md`, `platform/REBAC.md`

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
- become a team manager.

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

#### TeamManager

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

    define team_manager: [user, team]
    define team_editor: [user, team]
    define team_analyst: [user, team]
    define team_member: [user, team] or team_manager or team_editor or team_analyst

    define can_read_team_profile: team_member
    define can_manage_team_governance: team_manager
    define can_manage_team_roles: team_manager
    define can_update_resources: team_editor
    define can_update_agents: team_manager
    define can_run_evaluations: team_analyst or team_manager
    define can_manage_evaluation_corpus: team_analyst or team_manager
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
| team `owner` | Legacy governance authority | Review and grant `team_manager` if still valid |
| team `manager` | Ambiguous: may be content operator or governance delegate | Review; grant `team_manager` or `team_editor` explicitly |
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
    define team_manager: [user, team]
    define team_editor: [user, team]
    define team_analyst: [user, team]
    define team_member: [user, team] or team_manager or team_editor or team_analyst

    # Legacy, compatibility only
    define legacy_owner: [user, team]
    define legacy_manager: [user, team]
    define legacy_member: [user, team]

    # Compatibility bridge
    define can_manage_team_governance: team_manager or legacy_owner
    define can_update_resources: team_editor or legacy_manager
    define can_use_team_agents: team_member or legacy_member
```

Implementation may keep existing relation names (`owner`, `manager`, `member`) as the
legacy names to avoid tuple migration. The RFC requirement is that the target names and
the legacy bridge are documented separately.

## 17. Readiness Report

Before disabling the legacy bridge, Fred must provide a readiness report:

- teams with no `team_manager`;
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
| Active legacy owner accountable for process/compliance | `team_manager` |
| Active legacy manager curating corpus/content | `team_editor` |
| Active legacy manager responsible for compliance/process | `team_manager` |
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
5. Whether `team_manager` can grant `team_analyst`, or whether that requires a
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
`[user]` only (or the target `team_manager` direct-assign relation); `platform_admin`
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
`team_manager`, `team_editor`, `team_analyst`, `team_member`. No aliasing.

### 24.6 TeamAnalyst delegation (`§21.5`)

`team_manager` may grant `team_analyst` directly, consistent with `TeamManager` owning
team role delegation (`§3.2`). No separate platform-level approval step.

### 24.7 Implementation note (2026-07-09): team-bootstrap exception

Implementing `§24.2` as a blanket removal of `admin from organization` broke a
separate, documented requirement: `docs/swift/platform/REBAC.md`'s "locked design
authority" states team creation and first-manager assignment belong to the platform
admin, and no code path exists to assign a team's first owner other than that
escalation (there is no `create_team` flow that special-cases it). A completely
unscoped removal would leave newly created teams with no way to ever get an owner.

Resolution: `can_administer_owners` and `can_administer_managers` additionally accept
`platform_admin from organization` (the new, explicit, bootstrapped relation) — not
the legacy Keycloak-derived `admin`. Every other team capability
(`can_update_info`, `can_read_conversations`, `can_administer_members`, general team
membership) stays owner-only, with no platform-level escalation at all. This keeps
the team-bootstrap capability the product already committed to, while still closing
the actual security gap (a platform role reading/managing team content). Verified
against a live OpenFGA instance, not just the compiled schema JSON
(`fred_core/tests/integration/test_rebac.py::test_platform_admin_and_observer_never_grant_team_access`,
`::test_team_hierarchy_and_permissions`).

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

## Summary

The target is intentionally simple:

1. Keycloak authenticates.
2. Fred/OpenFGA authorizes.
3. Platform roles do not grant team data access.
4. Team roles are explicit.
5. Legacy roles survive only as a temporary, audited bridge.

This gives CVSSI a stable model to review and gives existing teams a safe migration
path that does not require a complex day-one Keycloak/OpenFGA rewrite.
