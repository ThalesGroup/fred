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

Existing contracts remain authoritative: [admin charter](../add-team-admin-charter/design.md)
(pending nominees have only member rights), [conversation filesystem](../add-deep-agent-conversation-filesystem/design.md)
(session ID remains its physical ownership key), and [application entitlement](../first-class-application-rebac/design.md)
(corpus authorization does not redefine application grants). The older
[version-retirement migration](../retire-document-versioning/specs/document-import-conflicts/spec.md)
handles legacy multi-folder input; it is not a permission model for this target.

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
| Admin | Team/project governance and habilitations | No implicit content access; explicit project roles required |

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
Use the same gate for corpus metadata, content, counters and service
identities. This change does not restore the retired general-purpose agent
filesystem. Folder summaries never load item IDs; document pages are separate.

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
not a description of shipped behavior. The broader RFC now links here for project rules and retains only the future
organization extension. Current-behavior docs are explicitly distinguished from
this proposal; replace their obsolete implementation details only when code lands.
Paths below are relative to `docs/swift/`.

| Document | Disposition |
| --- | --- |
| `rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md` | Project rules replaced by links to this change; only future organization work remains. |
| `platform/REBAC.md` | Keep canonical cross-capability overview; link shipped corpus rules and describe the space boundary. Preserve non-corpus policies. |
| `platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md` | Stale global app-role guidance replaced by the canonical ReBAC reference. |
| `design/INGESTION.md` | Keep operations; replace duplicated import rules with spec links and remove multiple-membership assumptions. |
| `design/KNOWLEDGE-BASE.md`, `design/RESOURCES-DASHBOARD.md` | Update sync moves, space ownership and eager item-list assumptions. |
| `backlog/AUTHZ-MIGRATION-BACKLOG.md` | Retain unresolved Step 6 obligations and historical references; scope clarified and dead registry link removed. Retirement requires their disposition first. |
| `rfc/RESOURCE-INGESTION-UX-RFC.md` | Trim settled portions after checking its remaining questions; retire only if none remains. |
| `rfc/DOCUMENT-VIEWER-AI-PANEL-RFC.md` | Keep unrelated open product decisions. |

No new RFC/status report or blanket deletion of historical documents.

## Risks / Trade-offs

- Larger product scope → include project UI, conversations and evaluation in
  acceptance, not just a new FGA type. Preserve ordinary conversation privacy.
- Hidden team-only assumptions → trace SDK/runtime grants, session stores, tools,
  quotas and generated APIs; explicit project context must survive every boundary.
- Governance versus content access → test admin-only callers as well as ordinary
  members; role-management authority must not bypass content checks.
- Multiple organizations later → explicit ancestry helps, but tenant isolation and
  onboarding remain separate work requiring their own validation.

## Governance decision and delivery

Team administration grants no implicit access to project documents, conversations
or evaluation datasets. Project membership permits corpus reading; analysis of
other members' conversations requires an explicit project analyst role. Roles may
be combined, but assignment remains explicit and audited. Administrating structure
and habilitations is distinct from exercising those content permissions.

This is Fred's design application of least privilege, not a claim that ANSSI
prescribes these exact product roles: see [ANSSI measures 0098/0101](https://monservicesecurise.cyber.gouv.fr/referentiel-mesures)
and [CNIL habilitation guidance](https://www.cnil.fr/fr/securite-gerer-les-habilitations).
Audit does not substitute for limiting access. Self-assignment rules need separate
specification before implementing role-management paths; explicit assignment alone
is not a barrier against a malicious administrator who can grant themselves roles.
Detailed revocation mechanisms also remain deferred.

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
