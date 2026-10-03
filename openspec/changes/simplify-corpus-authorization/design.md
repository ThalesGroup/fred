## Context

See [proposal](proposal.md). The target is space-owned authorization, replacing
this change's earlier folder-owned draft. Current `schema.fga` has team roles,
folder grants and document-parent tuples; corpus metadata stores `tag_ids`.
`SessionMetadataRow` has mandatory `team_id`, with no project context.
`DocumentScopeControlParams.bound_library_ids` already pins the chat picker
read-only; preserve existing modes rather than invent a nested-picker feature.

## Goals / Non-Goals

**Goals:** usable projects within the current organization; uniform space rights;
authorization cost independent of documents and folders inside a fixed context.
**Non-goals:** multiple-organization administration, arbitrary sharing, folder ACLs,
links/moves, new scope controls, online compatibility or detailed revocation design.
Personal spaces and session attachments retain their existing isolation.

## Decisions

### 1. An explicit ownership tree, not projects disguised as folders

Use the hierarchy `current organization → team → project`. A project has one
immutable team parent and its own registry, members and roles. Project members
must belong to its team; team membership alone grants no project access.
Keep team organization ancestry explicit so a future tenant boundary can be
introduced without deriving ownership from names or identifiers. This prepares
an extension point, not a claim that multi-tenant onboarding/isolation is solved.

Each corpus folder belongs to exactly one space; nested folders remain in that
space. Each document references one folder in canonical SQL metadata. Indexes
carry derived space/folder filters, never an independent authorization authority.
Remove corpus folder grants and document tuples from OpenFGA, retaining relations
needed for non-corpus resources. Reuse typed team/project ReBAC relations and the
existing facade; do not build a generic parallel authorization framework.

Organization-common resources, where exposed, are readable by all organization
members, never selected teams only. No new organization-management UI or role
redesign is included. Preserve existing personal and platform resource policies.

### 2. Roles stay at their assigned level

| Role | Team scope | Project scope |
| --- | --- | --- |
| Member | Reads common team corpus | Reads all corpus of projects joined |
| Editor | Manages team corpus/agents | Requires explicit project editor role |
| Analyst | Analyzes team conversations/datasets | Requires explicit project analyst role |
| Admin | Team governance | Transversal governance read is provisional; see review gate |

Project roles have the corresponding scoped responsibilities; being a project
member does not make every conversation visible to every other member. Project
analysts can analyze project history, including conversations predating their
appointment; derived datasets remain in that project. One person can be analyst
in multiple projects and several analysts can serve the same project.
Role grants/removals record actor, subject, role, space and time in existing audit
infrastructure, without introducing another approval workflow.

Carry forward the RFC's project bootstrap: team admin/editor creates a project
and nominates project admins among team members; creation grants no implicit
project content role. Project admins manage its membership. Read inherited common
resources does not confer write rights at their owning level.

### 3. Conversation space determines reach; agent configuration narrows it

An agent defined at team level can be used in that team's projects without being
copied. A project-defined agent stays in that project. A conversation has an
immutable, server-validated space; entering another space starts a new conversation.
Propagate that context through session metadata/history, execution/delegation,
attachments, tools and evaluation; a caller-provided project ID is not authority.

For a project conversation, contextual corpus = that project + its parent team's
common resources + applicable existing organization/platform common resources.
For a team conversation, it excludes all project content, including projects the
user belongs to. Governance permissions must not silently broaden ordinary chat.
Intersect this envelope with agent configuration and the current chat selection
where that control is enabled. Folder selection includes descendants. A configured
fixed scope remains fixed; no scope selection means the contextual envelope,
subject to agent restrictions. Preserve document selection where already supported.
Agent configuration can reference its owning level or ancestors, never a sibling
or descendant project. Empty intersections never fall back to global search.

Outputs, memory and evaluation datasets stay in the conversation space; inherited
agent authorship conveys no access to project conversations. User-visible context
and audit evidence identify user, space, agent/configuration, effective scope and
source references, reusing existing observability rather than logging content twice.

### 4. Authorize spaces before searching

Resolve canonical ancestry and check the required ReBAC permission once per
relevant distinct space within a request. Then constrain SQL/vector/tabular queries
by authorized space and selected folder subtree/document IDs before ranking.
This replaces the earlier proposal to rank globally and discard unauthorized
candidates: that approach risks starving relevant authorized results.
Validate returned hits against canonical membership in bulk to reject stale or
missing rows. This is integrity checking, not per-document permission evaluation.
Use the same gate for metadata, content, counters, agent filesystem and service
identities. Folder summaries never load item IDs; document pages are separate.

Let E be the fixed number of applicable ancestor/current spaces, P a finite page
of candidate projects, B the check batch size and A the finite attempt budget.
For a fixed relation, corpus access checks at most E spaces and project discovery
at most P candidates; transport calls are bounded by `ceil(checks / B) * A`.
No bound depends on folder/document count. E does not include sibling projects.
Discovery uses stable cursors and explicit continuation, including empty authorized
pages; it does not replace document ListObjects with unlimited project ListObjects.
Enforce input/page/retry limits and measure whole-turn tool invocations as well as
individual requests. SQL/vector cost and total multi-tool turn cost are separate
from the permission bound; never claim constant overall query latency.

### 5. Single membership across the lifecycle

Creation needs one authorized destination; overwrite preserves UID, folder and
space. Reject reparenting, multi-folder/unfiled corpus input and source-sync path
moves before mutation. Enforce same-folder name conflicts transactionally.
Keep session attachments separate. Clean-format import/export preserves ownership
and space roles; old archives require the separate translator. Project corpus is
charged once to the parent team's existing quota; no separate project quota UI.
Deletion and retried ingestion must not expose orphan rows or stale index content;
reuse existing lifecycle machinery and specify its detailed sequencing later.
Project access removal follows the team-removal principle; invalidating active
sessions, caches or streams is deferred to a focused revocation design.

### 6. Documentation consolidation

This change is the proposed authority for the scoped team/project target; it is
not a description of shipped behavior. Reconcile the broader RFC before declaring
the specification approved, then update shipped docs when implementation lands.
Paths below are relative to `docs/swift/`.

| Document | Disposition |
| --- | --- |
| `rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md` | Link its project slice here; remove duplicate target rules. Replace I5 (editor/analyst transversal read) and folder-ACL inheritance assumptions; keep multi-organization/onboarding work and identify the admin review gate. |
| `platform/REBAC.md` | Keep canonical cross-capability overview; link shipped corpus rules and describe the space boundary. Preserve non-corpus policies. |
| `platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md` | Correct the stale global admin/editor/viewer RBAC opening; link the identity/ReBAC contract. |
| `design/INGESTION.md` | Keep operations; replace duplicated import rules with spec links and remove multiple-membership assumptions. |
| `design/KNOWLEDGE-BASE.md`, `design/RESOURCES-DASHBOARD.md` | Update sync moves, space ownership and eager item-list assumptions. |
| `backlog/AUTHZ-MIGRATION-BACKLOG.md` | Retirement candidate: closed #1875, deleted registry link and mixed statuses. Preserve useful guardrails and repoint references before retirement. |
| `rfc/RESOURCE-INGESTION-UX-RFC.md` | Trim settled portions after checking its remaining questions; retire only if none remains. |
| `rfc/DOCUMENT-VIEWER-AI-PANEL-RFC.md` | Keep unrelated open product decisions. |

No new RFC/status report or blanket deletion of historical documents.

## Risks / Trade-offs

- Larger product scope → include project UI, conversations and evaluation in
  acceptance, not just a new FGA type. Preserve ordinary conversation privacy.
- Hidden team-only assumptions → trace SDK/runtime grants, session stores, tools,
  quotas and generated APIs; explicit project context must survive every boundary.
- Pending governance decision → no new transversal permission silently implemented.
- Multiple organizations later → explicit ancestry helps, but tenant isolation and
  onboarding remain separate work requiring their own validation.

## Review gates and delivery

The team-admin read of project documents, conversations and datasets is a working
hypothesis, not approved policy. It grants neither editor/analyst mutation powers
nor permission to publish project content at team level. Resolve this gate before
implementing that relation. No detailed revocation mechanism is selected here.

Keep this PR specification-only. Subsequent dependent PRs should group coherent
project foundations, corpus conversion, then context/consumer integration, with
checks in each layer. Final boundaries require a dependency review before coding;
a broken intermediate layer must not land on Swift merely because it is reviewable.
The whole project feature requires end-to-end validation before release. Do not
create stack branches until the user selects their names.

## Migration Plan

Validate against isolated empty data, without resetting Monday's environment.
The separate offline translator, with the platform stopped, must reconcile old
grants and memberships explicitly; this target must not silently widen access to
formerly restricted folders. Fresh-install success is not upgrade approval.
Backup/restore and release impact classification belong to that later delivery.
