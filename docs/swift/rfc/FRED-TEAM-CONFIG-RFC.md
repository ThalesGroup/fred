# RFC — Fred Team Configuration: Ownership, Objects, and Authorization Boundaries

**Status:** Draft for team review  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-23  
**Area:** `control-plane-backend`, `frontend`, `fred-runtime`, `knowledge-flow-backend`  
**Related:** `TEAM-PLATFORM-POLICY-RFC.md`, `TEAM-ROUTING-POLICY-RFC.md`,
`../design/PROMPTS.md`, `PROMPT-SYSTEM-HARDENING-RFC.md`

---

## 1. Problem

Fred does not yet expose a clear, first-class product model for team configuration.

Today:

- team settings in control-plane are limited to metadata such as description,
  privacy, and banner
- platform-enforced team settings such as upload caps, ingestion limits, or
  allowed model/tool sets do not exist as a typed team object
- runtime model routing already supports team-aware and operation-aware decisions,
  but the control-plane does not yet own a team-level routing policy surface
- team and personal prompts exist as a product idea, but prompt ownership,
  authorization, and personal scope semantics are not yet fully aligned
- several current team-scoped write surfaces are weaker than the intended role
  model and must not be used as the foundation for new UI

This RFC defines the target state that must exist before implementation starts.

---

## 2. Goals

1. Define one simple and explicit product model for team configuration.
2. Separate platform-owned concerns from business-owned concerns.
3. Define which team actor is allowed to configure which surface.
4. Keep prompt libraries independent from agents while making them reusable by
   agent creation and conversations.
5. Produce a stable contract that later implementation work can follow without
   rediscovering product boundaries.

---

## 3. Non-goals

This RFC does not implement:

- backend APIs
- database migrations
- frontend pages or forms
- runtime wiring
- Knowledge Flow enforcement code
- authorization fixes

This RFC is design authority only.

---

## 4. Actor model

Fred team configuration uses four product actors.

### 4.1 Team member

A normal end user of the team.

Can:

- use team-managed agents
- use prompts that are visible in their team context
- manage their own personal prompts

Cannot:

- change team platform policy
- change team routing policy
- curate shared team prompts

### 4.2 Business admin

The operator responsible for how the team's agents behave from a business point
of view.

Target mapping in Fred: team `manager`.

Can:

- configure team routing policy
- manage shared team prompts
- curate prompt scores
- use team resources and team agent-management surfaces

Cannot:

- relax or override platform guardrails defined for the team

### 4.3 Platform admin

The operator responsible for team governance and platform-level safety.

Target mapping in Fred: team `owner`.

Can:

- create a team and define its initial metadata
- assign and revoke the team manager role
- define and update `TeamPlatformPolicy` (quotas, allowlists, enforced limits)
- read any team configuration surface for audit purposes

Cannot:

- create, edit, or delete agent instances
- create, edit, or delete shared or personal prompts
- set or update `TeamRoutingPolicy`

### 4.4 Deployment admin

The deployment-level administrator outside one single team.

This actor is out of scope for day-to-day product UI.

Note: team creation and manager assignment are product actions performed by the
platform admin (§4.3) through the product UI. They are not assumed to require
a deployment script. Deployment scripts bootstrap the very first platform admin
relation only.

Design rule for this track:

- product contracts must not rely on implicit global-admin escalation for team
  writes
- every team-scoped write must still pass explicit team-scoped authorization
  rules

This keeps the product contract aligned with `docs/swift/platform/REBAC.md`
even if legacy schema details are corrected later.

---

## 5. Team configuration objects

Fred team configuration is split into four distinct objects.

| Object               | Purpose                                                            | Primary owner                                         |
| -------------------- | ------------------------------------------------------------------ | ----------------------------------------------------- |
| `TeamMetadata`       | Basic presentation metadata: name, description, banner, visibility | owner                                                 |
| `TeamPlatformPolicy` | Platform-enforced limits and allowlists                            | owner                                                 |
| `TeamRoutingPolicy`  | Team-wide model-routing behavior for managed execution             | manager                                               |
| `TeamPromptLibrary`  | Reusable prompts outside agents, both personal and shared          | manager for shared prompts, user for personal prompts |

These objects must stay separate.

### 5.1 TeamMetadata

This remains intentionally small:

- description
- privacy
- banner

It must not absorb routing policy, prompt curation, or upload quotas.

### 5.2 TeamPlatformPolicy

This object defines hard guardrails for a team.

Examples:

- maximum upload size
- maximum ingestion source file size
- maximum user object-store footprint
- allowed model profiles
- allowed MCP servers

It is the contract that bounds what business admins are allowed to configure.

### 5.3 TeamRoutingPolicy

This object defines how the team's managed agents choose models at runtime.

Examples:

- all chat phases for this team use one default model profile
- planning uses a stronger profile
- self-check uses a cheaper profile

It is business-owned, but every referenced profile must be allowed by
`TeamPlatformPolicy`.

### 5.4 TeamPromptLibrary

This object defines reusable prompts that are authored outside agents.

It has two scopes:

- personal prompts, owned by exactly one user
- shared team prompts, curated by business admins

The library remains independent from agents:

- agent import is copy-by-value
- conversations keep a live session-level reference for context prompts

---

## 6. Ownership matrix

| Surface                         | Member read                       | Manager write      | Owner write        | Notes                                                      |
| ------------------------------- | --------------------------------- | ------------------ | ------------------ | ---------------------------------------------------------- |
| Team metadata                   | Yes, if team visible              | No                 | Yes                | Existing metadata-only surface                             |
| Team platform policy            | No direct self-service            | No                 | Yes                | Owner-managed guardrails                                   |
| Team routing policy             | No direct self-service            | Yes                | **No**             | Routing policy is manager-owned; owner has no write access |
| Team shared prompt CRUD         | Read when visible in team context | Yes                | Yes                | Business-owned shared library                              |
| Personal prompt CRUD            | Own prompts only                  | N/A                | N/A                | User-owned, never shared by write permission               |
| Prompt score                    | No                                | Yes                | Yes                | Team prompts only                                          |
| Prompt promote personal -> team | No                                | Yes on target team | Yes on target team | Target-team curation action                                |
| Prompt promote team -> team     | No                                | Yes on both teams  | Yes on both teams  | Copy-by-value between curated spaces                       |

The key rule is:

- platform policy is owner-owned
- routing policy is manager-owned
- shared prompts are manager-owned
- personal prompts are user-owned

---

## 7. Authorization principles

### 7.1 Do not use membership-only checks for writes

Any team-scoped write added for this track must require the correct explicit team
permission. Membership or public readability must never be enough.

### 7.2 Owner and manager are orthogonal, not hierarchical

This is the most important rule in this RFC.

- Owner has full authority over governance (`TeamPlatformPolicy`, team creation,
  manager assignment) and **zero write authority** over agents, prompts, and
  routing policy.
- Manager has full authority over the business surface (`TeamRoutingPolicy`,
  agent instances, shared prompts) and **zero write authority** over platform
  policy.

There is no "owner supersedes manager" escalation on the business surface.
Owner can only constrain what manager is allowed to do (via platform policy
limits), not override their decisions directly.

This must be enforced at the API layer, not only in the UI.

### 7.3 Permission name mapping

Before introducing new permission names, the initial mapping is:

- owner-only surfaces map to the same trust boundary as `can_update_info`
- manager-owned agent and routing surfaces map to the same trust boundary as
  `can_update_agents`
- manager-owned shared prompt curation maps to the same trust boundary as
  `can_update_resources`

TEAM-02 will produce the frozen permission table. Until then, §7.2 is the
authoritative rule; the names above are provisional.

### 7.4 Policy tightening does not immediately break existing configuration

When a platform admin tightens `TeamPlatformPolicy` (removes a model profile,
lowers a quota, removes an MCP server from the allowlist):

- existing agent instances that reference a now-disallowed value are flagged
  as policy-drift, not broken immediately
- they continue to execute under the previously allowed configuration until
  the team admin re-saves or remediates the instance
- new enrollments and updates must pass the current policy at write time
- it is the responsibility of TEAM-04 to enforce this at the boundary

This fail-soft-flag approach prevents platform admin changes from silently
breaking live team operations while still enforcing policy on all new writes.

### 7.5 Personal scope is never represented by shared team membership

Personal prompts are not "shared prompts under team id `personal`".

They are prompts owned by one caller inside the reserved `/teams/personal`
route family — the same system team already used for personal sessions. No
new team object is needed for personal prompt scope.

---

## 8. Current-state blockers that must be treated as design inputs

The following observed gaps are not implementation tasks in this RFC, but they
must shape the target contracts:

1. Some current agent, prompt, and session write surfaces accept team read
   authorization where a stronger write permission is expected.
2. Some current list/detail routes skip explicit team authorization entirely.
3. Personal prompts are currently at risk of collapsing into one shared
   `personal` namespace.
4. Prompt promotion and prompt score authorization are weaker than the intended
   governance model.
5. Team configuration does not yet exist as a typed product object beyond
   metadata.
6. Platform policy examples such as upload or ingestion caps are not modeled at
   team scope today.
7. Runtime supports routing by team and operation, but there is no team-owned
   control-plane routing contract yet.

No new UI should be built on top of those gaps without first resolving them in
implementation.

---

## 9. Required RFC set

This RFC is the umbrella contract. The implementation phase must also follow:

1. [`TEAM-PLATFORM-POLICY-RFC.md`](./TEAM-PLATFORM-POLICY-RFC.md)
2. [`TEAM-ROUTING-POLICY-RFC.md`](./TEAM-ROUTING-POLICY-RFC.md)
3. Current prompt scope: [`PROMPTS.md`](../design/PROMPTS.md)
4. Prompt hardening: [`PROMPT-SYSTEM-HARDENING-RFC.md`](./PROMPT-SYSTEM-HARDENING-RFC.md)

Together, these documents are the design authority for the future team
configuration track.

---

## 10. Implementation sequence mandated by this RFC

Future implementation must proceed in this order:

1. authorization hardening for existing team-scoped surfaces
2. team platform policy storage and API contract (includes team creation endpoint)
3. platform policy enforcement in upload, ingestion, and agent configuration
4. team routing policy storage and runtime propagation
5. prompt-library scope and governance realignment
6. frontend team settings and prompt UX work

The UI phase starts only after steps 1 through 5 are complete enough to provide
stable backend contracts.

---

## 12. Team creation lifecycle

Team creation is the entry point for the whole configuration track. It is
specified in full in `TEAM-PLATFORM-POLICY-RFC.md §13`. Key points reproduced
here for navigability:

- Platform admin creates a team via `POST /control-plane/v1/teams` with an
  initial platform policy (optional; deployment defaults apply if omitted).
- The designated `admin_user_id` receives the `owner` ReBAC relation and is
  added to the Keycloak group in the same call.
- Personal teams are created automatically on user creation; the same creation
  logic applies but uses `personal` defaults and `max_users = 1` (immutable).

### 12.1 Actor responsibilities at creation time

| Actor | Responsibility |
|---|---|
| Platform admin | chooses team name, designates team admin, optionally overrides platform policy |
| Team admin (designated) | receives owner role; can immediately configure routing policy |
| System | creates Keycloak group, inserts ReBAC relations, writes resolved platform policy |

### 12.2 Post-creation configuration flow

```
Team created
    │
    ├─► Platform admin: PATCH /teams/{id}/platform-policy   (optional tuning)
    │
    └─► Team admin:     PATCH /teams/{id}/routing-policy    (business settings)
                        GET   /teams/{id}/platform-policy   (read-only view)
```

The two surfaces are independent: routing policy can be configured before
platform policy is tuned, and vice versa. Both read from the same resolved
policy at enforcement time.

---

## 13. Task activity surfaces

Long-running operations (document ingestion, user deletion, migration steps)
emit structured events via the unified task event stream (OPS-04 RFC). Each
task carries a `team_id` that determines who can see it.

### 13.1 Team activity view

Team admins (owner or manager) see all tasks scoped to their team via
`GET /api/v1/tasks?scope=team&team_id={id}`. This covers:

- document ingestion tasks triggered by any team member
- admin tasks affecting the team (e.g. delete-user operations)

This view is a dashboard only — no content, no document titles, no conversation
text. Step labels and error messages are operational metadata (see OPS-04 RFC
§7.3 content boundary rule).

Route: `/settings/team/activity`  
Owner: team admin (owner or manager)

### 13.2 Platform admin task dashboard

Platform admins see all tasks across all teams via
`GET /api/v1/tasks?scope=platform`. This adds:

- platform-level tasks (migration steps, `team_id = NULL`)
- the same team-scoped tasks visible to each team admin

Route: `/admin/tasks`  
Owner: platform admin only

### 13.3 What these surfaces do NOT replace

The per-user task tray in the sidebar shows tasks the current user triggered,
with live SSE progress. The team and platform dashboards are polling overviews
for admin situational awareness. They are additive, not duplicative.

---

## 11. Acceptance criteria for team review

This RFC set is ready for implementation only when the team agrees that:

- the distinction between platform admin and business admin is explicit
- the four product objects are the right split
- shared prompts are treated as team resources, not agent fields
- personal prompts are truly personal while keeping the existing `/teams/personal`
  route family
- routing policy is bounded by platform policy
- implementation order prevents frontend churn caused by unclear ownership
