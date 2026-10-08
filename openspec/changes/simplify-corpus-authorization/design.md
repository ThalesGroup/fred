## Context

See [proposal](proposal.md). Inspection of `swift` at
`6a0c3e8963fdcf6e1fcef7498f5c2dbfa19dc957` found:
`metadata.tag_ids` plus FGA document-parent tuples; tag listings loading item IDs;
document permission lookups in metadata/search; mandatory `team_id` on managed
agents and sessions; runtime validation equating agent ownership with execution
team; and platform roles/catalog anchors on singleton `organization:fred`.
The existing [organization RFC](../../../docs/swift/rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md)
describes the earlier split delivery. This change supersedes that split for the
scope below; neither document is a claim about shipped behavior.

## Goals / Non-Goals

**Goals:** one explicit ownership model; uniform space permissions; less owned
production code and fewer live authorization paths; bounded authorization;
organizations and usable projects delivered in one major-version PR with offline
translation and a rehearsed restore.

**Non-goals:** arbitrary container hierarchies, document movement/sharing, a second
permission engine, old/new runtime compatibility, organization-creation UI,
new organization wiki or analytics workflows, tenant transfers, cancellation of
in-flight operations, and automatic resolution of inconsistent migration mappings.

Keep [team admin charter](../add-team-admin-charter/design.md) behavior (pending
nominees are not active admins), [conversation filesystem](../add-deep-agent-conversation-filesystem/design.md)
session ownership, and [application entitlement](../first-class-application-rebac/design.md)
policies. Adapt their context where needed rather than duplicating their services.
The IdP supplies identity; Fred/OpenFGA supplies authorization.

## Decisions

### 1. One bounded SQL ownership identity

Use a shared `space` identity/ancestry table with a closed discriminator:
organization, team or project. An organization is a root, a team has an organization
parent, and a project has a collaborative-team parent. Existing team-specific
settings remain a one-to-one extension; the structural team kind and personal
owner live on the space identity so typed foreign keys exclude personal-team
project parents. Preserve existing IDs. This replaces ambiguous ownership
references instead of adding a second tree beside `teammetadata`.

| Record | Canonical structural information |
| --- | --- |
| Space | ID, kind, name, immutable typed parent; team kind and unique personal owner; root organizations have no parent |
| User | Explicit organization reference; never selected from first joined team or an IdP role |
| Team settings | Team-space reference and existing settings |
| Corpus folder | Space reference, local parent folder and name |
| Corpus document | One folder reference and scalar document name; no membership array |
| Managed agent | Owning space reference, existing runtime binding and tuning |
| Conversation | Immutable execution-space reference and owner; existing session ID retained |

Use foreign keys, shape checks and scoped uniqueness for collocated tables.
A composite parent reference including the parent's kind can enforce the closed
space hierarchy; ordinary service conventions are not a substitute. Folder
parentage must preserve space identity. Document names are unique within a folder;
team names are scoped to the organization and project names to their parent team.
Keep expandable metadata in JSON, but not the authoritative ownership keys.
Across separately owned runtime/evaluation databases, propagate validated IDs and
enforce the contract at the boundary; do not promise cross-database foreign keys.
Preserve per-backend Alembic ownership and one linear head.

Every admitted user has one organization, one or more collaborative teams and
one personal team in that organization. An authenticated newcomer may have an
identity with no organization; this is not workspace admission. Such a person can
request organization membership through restricted onboarding and cannot use a
personal workspace, corpus, agents or conversations before admission. The missing
organization represents non-admission; do not add a parallel user-status model.
Explicit provisioning or approved admission supplies the organization and initial
team assignment before workspace use; identity synchronization must not guess them.
Default-team enrollment and open-team
discovery are restricted to the user's organization. Removing the last collaborative
membership requires an explicit replacement or the existing account-removal path.

Organization requests use the same membership service, request lifecycle and UI
pattern as team admission, owned by the control-plane. Reuse its audited role
writes; SQL request records are not a role mirror. Approval belongs to an active
admin of the requested organization and admits the person as member, joins an
explicit open welcome team in that organization and establishes their personal
team. This does not authorize admission to a closed team by a parent admin.
An incomplete admission grants no workspace access. A competing approval cannot
assign a second organization. Keep this a bounded membership feature, not a generic
workflow/notification framework, and add no checks to the corpus hot path merely
to consult request status.

Deliver the shared request/approval flow for organizations and closed collaborative
teams in this version. A team request requires existing membership of its
organization and is decided by its active local team admin. Existing direct admin
admission remains available; open-team joining remains immediate. Do not extend
requests to projects or personal teams. Reuse one request representation and
decision path, with target-specific eligibility and admission rules.

Alternative rejected: three nullable owner columns or an untyped owner kind/ID on
every consumer. A small common structural identity avoids repeated ownership
branches and provides a real FK target. It is not a configurable tenancy framework.

### 2. ReBAC roles and structural ownership have named owners

SQL owns object existence and parentage; FGA owns role grants. Parent relations
required by FGA are projections of canonical SQL, not an independently editable
tree. Role writes validate the subject's organization and the target's ancestry.
Do not introduce a SQL role mirror or a generic synchronization service.

Separate `platform` from `organization`: platform roles and catalog anchors leave
the historical singleton. Organization/team/project support member, editor,
analyst and admin, cumulatively; elevated local roles include local member rights.
Organization member rights permit common corpus/agent use. Organization analyst
does not grant descendant analysis or create a new analytics workflow.
Editor/analyst authority is explicit: local admin may self-grant either with audit.
Organization admin creates teams; team admin alone creates projects. New-space
bootstrap may nominate its creator; existing closed-space admission and admin
nomination belong to an active local admin. Parent governance must not expose a
standing role-write bypass. Existing open teams permit ordinary member self-join
inside one organization, including by someone who also holds an admin role.

Project permissions require both local project roles and parent-team membership.
Team removal therefore denies the next project request even before remaining
project tuples are cleaned; the removal lifecycle also deletes those roles.
Personal spaces admit only their owner; no organization/team administration
path may grant another person access. Provision their structural and role records
explicitly rather than maintaining personal-user versus personal-team corpus models.

Keep existing platform-only operational functions distinct from content access.
Translate old platform roles and organization assignments explicitly; do not turn
`platform_admin` into a descendant member. Consolidate overlapping team-governance
roles rather than retain a parallel global team-manager path.

Alternative rejected: blanket descendant role inheritance. It conflicts with
local analysis/editing and turns governance into content access.

### 3. Conversation context, not agent ownership, determines execution reach

An organization agent can serve its organization's teams/personal teams/projects;
a team agent can serve its own team and projects; a project agent stays local.
Resolve the agent owner and conversation space separately, validating ancestry
server-side. The current runtime owner-team equality check becomes this explicit
compatibility rule, not an unchecked removal of the guard.

| Conversation space | Maximum corpus envelope |
| --- | --- |
| Collaborative team | That team's corpus and organization-common corpus |
| Project | That project, parent team's common corpus and organization-common corpus |
| Personal team | Its private corpus and organization-common corpus |

Retain already-supported platform-common resources where applicable; no
platform-owned agents are introduced. Intersect this envelope with agent restrictions
and existing chat scope controls. Folder selection includes descendants. Omitted
selection means the contextual envelope; an explicit empty/invalid intersection
never means global access. No new scope widget variants.

Session metadata, runtime history, tool/delegation requests, memory, generated
content and evaluation carry the immutable execution context. Changing space means
another conversation. Agent authorship grants no access to descendant conversations.
Keep attachments session-owned. Model/capability entitlement, routing and quota
consumers use the validated execution team (project's parent team when needed);
common agent ownership must not lend another team's entitlements.

Alternative rejected: copying an inherited agent into each project. It duplicates
configuration and lifecycle rather than representing reuse.

### 4. A small permission decision before retrieval

Resolve canonical context, check each required permission on each relevant space
once per protected request, then constrain SQL/vector/tabular candidates before
ranking. Direct content, metadata, counts, citations and tools use the same gate.
Service identities carry a server-validated execution scope; a supplied team or
project ID alone is never authority. Validate returned index hits against canonical
SQL membership in a batch; that is integrity checking, not document ACL evaluation.

For E applicable spaces, R required relations, batch capacity B and finite attempt
budget A, logical space checks are bounded by E * R and transport attempts by
ceil((E * R) / B) * A when batched. Current/ancestor business spaces are at most
three; account/platform admission is accounted for separately. Existing batching
may need its existing facade extended across objects, not a parallel engine.
No bound depends on document count, folder count or folder depth. Paginated
discovery is measured separately; never replace unlimited document ListObjects
with unlimited project ListObjects.

After a successful revocation, the next protected request must observe it,
including requests from an open conversation. Use authoritative FGA reads through
the existing higher-consistency support; do not reuse positive authorization
decisions across requests. Request-local reuse is allowed. Already-authorized
operations may finish; subsequent tool HTTP requests reauthorize. No stream
cancellation system or distributed permission cache is added.

Alternative rejected: caching growing document permission lists or discarding
unauthorized hits after global ranking. Both preserve the expensive model.

### 5. Converge live consumers before deleting old paths

| Current path | Replacement and deletion condition |
| --- | --- |
| Corpus document-parent tuples and their writers | SQL folder membership; remove only after every corpus writer/read is converted |
| Document permission loops/global readable-ID lists | Space gate and bounded SQL/index filtering; include direct-ID and service callers |
| Folder grants and permission projections | Local space role permissions; retain FGA tag/resource behavior still used by non-corpus resources |
| Document `tag_ids` arrays and membership diffs | One corpus folder; retain unrelated descriptive labels |
| Folder responses containing every item ID | Folder summaries plus paginated documents; adapt deletion/list consumers together |
| Personal user-owned versus team-owned corpus branches | Explicit personal-team space and owner-only permissions |
| Agent owner team used as conversation context | Separate canonical owner and immutable execution space |

Preserve synchronized-source write restrictions, overwrite identity, transactional
name-conflict handling and deletion/ingestion lifecycle. No new document move is
introduced. Project storage is charged once to its parent team's existing quota;
no project quota UI. Corpus ownership changes must preserve personal/platform
resource policies and avoid charging inherited reads to the consuming space.

`tag` also serves non-corpus resources. Some CSV/Excel attachments occupy metadata
rows with no corpus folder. Model that existing distinction explicitly; do not
force attachments into the corpus or delete all tag/resource authorization.
Candidate deletions are not savings until static and dynamic consumers are checked.

## Governance decision and delivery

Use one topic branch and one draft implementation PR targeting `swift`.
A planning commit precedes six implementation stages in [tasks](tasks.md):
SQL/FGA foundation; administration; corpus conversion; execution/consumers;
offline cutover; close-out. Commit completed single-purpose blocks within a stage;
do not create a stack or a separate planning PR. Intermediate commits stay on the
topic branch; merge only the fully integrated major-version outcome.

Before code, capture the baseline commit, corpus sizes, permissions, request/turn
call counts, transport attempts, rows read and latency under the same controlled
workload used at the end. Reuse existing fixtures/metrics/campaign tooling.
Include real OpenFGA/PostgreSQL, multiple organizations, 200 teams/2,000 users and
growing document/folder counts; isolate this from developer/customer environments.

Each stage records its commit, targeted verification and gross production
additions/deletions plus net change in the existing task/PR evidence. Separate
tests, generated files, schema/migration/tooling and documentation. Also record
removed concepts/paths. The cumulative goal is less owned production code; an
unmet goal needs an explicit disposition, never compressed code or removed tests.

Run only risk-directed checks during implementation. At integration, run root
quality, the complete applicable offline suites, real-store authorization/migration
scenarios, matched performance measurements and one full author/independent branch
review. Fix findings together and rerun affected checks; broaden only when impact
or failures invalidate prior evidence. A focused stage review is not a full PR
review and a changed commit does not inherit invalidated evidence.

## Risks / Trade-offs

- Shared space identity touches many consumers -> migrate existing owners in the
  same branch; retain useful team settings and shared primitives, not duplicate APIs.
- SQL/FGA span stores -> admission validates canonical objects and ancestry;
  successful mutations require their relevant writes to complete. Reuse existing
  lifecycle handling; no unreviewed recovery framework.
- Organization isolation extends beyond documents -> scope user directories,
  team discovery/default enrollment, content URLs, history, evaluation and service
  calls; restrict platform administration to its established operational surfaces.
- Current admins can run/manage evaluations without analyst -> align content-bearing
  evaluation actions with the agreed explicit analyst role and document the break.
- Source data outside the target invariants -> report unsupported data and stop the
  offline procedure; never invent projects, duplicate accounts or widen access.
- Existing charter/rescue behavior -> retain its legitimate account/lifecycle
  handling, but do not use rescue as self-admission to an occupied closed space.

## Migration Plan

This same major-release PR delivers the separate operator tool. Alembic owns
relational DDL; the tool coordinates data translation, FGA model/tuple conversion
and index preparation. Do not add startup translators, feature switches,
legacy fallbacks, dual writes/reads or mixed-version deployment support.
Its organization/allocation/initial-role inputs are supplied in an explicit
external JSON file, as approved by the developer; this is not service startup
configuration. Further configuration choices require developer confirmation.

1. Stop ingress, backends and workers that can mutate the affected stores.
2. Take and verify a coordinated backup of application/runtime/evaluation
   PostgreSQL, FGA model/tuples, relevant content and index state, and the old
   binaries/configuration. Existing application export excludes FGA/files and is
   not a complete backup.
3. Supply organizations to create, team-to-organization assignments and initial
   organization role assignments. Derive each existing user's unique organization
   from the supplied team allocation and attach its personal team there. Allocation
   coherence is an operator precondition; no automatic conflict resolver.
4. Before conversion, verify source ownership and grants are representable by
   the target roles. Refuse unsupported multi-folder/ambiguous ownership or
   exceptional folder ACLs, including a private personal folder shared with another
   user; never silently discard or widen a grant. Translate supported source rows
   preserving document/session/agent IDs, memberships, privacy and corpus role
   permissions. Create no projects. Apply the evaluation-role change explicitly, with affected
   grants reported; do not silently manufacture analyst access.
5. Convert FGA platform/space relations; remove corpus ACL state. Populate the
   new index filters from canonical SQL, preserving vectors where possible.
   Validate structural constraints, authorization samples, quotas and counts before
   restart. Installation uses the same target schema with empty data.
6. Restart one new version and run the agreed acceptance scenarios. On failure,
   remain stopped until explicitly repaired or restore the whole previous snapshot
   and old version. No automatic retry/compensation or reverse semantic migration.

Rehearse both migration and restore on an isolated representative copy. Restore
returns to the pre-cutover snapshot; writes made after reopening are not preserved
by that rollback. Record exact tool commands once implemented, input format,
backup boundaries and results in the PR's major-impact operator migration note.

At close-out, reconcile the organization RFC, ReBAC overview, product/runtime
contracts, ingestion/resource docs, supported frontend help and source-sync
guidance. Keep current-behavior docs truthful until implementation lands; remove
superseded planning rules rather than maintaining two authorities. Sync/archive
the change only after implementation, verification and review are complete.
