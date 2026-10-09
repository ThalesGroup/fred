## Why

Fred needs explicit organizations and projects while reducing the code and work
required to authorize its corpus. A major-version cutover lets one space-owned
model replace folder/document ACLs without carrying two runtime architectures.

Tracking: [#2921](https://github.com/ThalesGroup/fred/issues/2921).
The earlier planning issue [#2938](https://github.com/ThalesGroup/fred/issues/2938)
is historical; this change incorporates the developer decisions of 2026-10-08.

## What Changes

- **BREAKING**: introduce explicit organization/team/project ownership and four
  cumulative local roles: member, editor, analyst and admin. Each admitted user belongs to
  exactly one organization, at least one collaborative team, and one private
  personal team. Organization assignment is explicit, not inferred at first join.
- **BREAKING**: corpus documents have one immutable folder and owning space;
  folders classify content without independent grants or cross-space sharing.
  Remove corpus document/folder FGA tuples and global authorization ID lists.
- Allow an authenticated newcomer without an organization to request admission.
  Until approval, expose only the restricted onboarding flow, with no personal
  workspace or corpus access. Organization admission establishes membership,
  an initial open welcome-team membership and the owner-only personal team.
  Include requests to closed teams in the same version and share the admission
  implementation and interaction pattern with team joining;
  do not introduce an organization-specific request engine.
- Preserve the distinction between governance and content. Only team admins
  create projects; they can nominate themselves at creation. Admission to an
  existing closed descendant requires its local admin. Local admins may grant
  themselves editor/analyst, with audit. Existing open teams remain joinable
  within their organization; projects require explicit admission.
- Bind conversations to their initial team/project. Reuse organization/team
  agents in descendant execution spaces; scope reads to local and ancestor-common
  content, narrowed by agent configuration. Personal content stays private;
  personal spaces may consume organization-common corpus and agents.
- Authorize before retrieval with work independent of corpus size. Recheck access
  on the next protected request after revocation, including open conversations;
  do not add interruption of already-authorized work.
- Deliver a separate offline migration tool: configurable organizations and team
  assignments, no initial projects, preserved identities, coordinated backup and
  restore. No compatibility switches, dual reads/writes or rolling mixed versions.
- First complete the simplified backend foundation, including corpus/execution
  consumers and deletion of superseded authorization paths; measure code reduction,
  call counts and isolation before returning to import/export or UI work.
- Then use the existing demo-bundle import as the integrated provisioning path:
  start an empty platform, build the demo archive, then import one organization
  with its users, teams and local roles. Replace the existing bundle contract with
  one organization per bundle and symmetric organization-scoped export, initially
  reserved to platform admins. Reuse control-plane services rather than creating
  a second provisioning implementation.
- Deliver in one topic branch and one PR, through precise commits and six
  validated stages. Measure production additions/deletions separately from tests,
  generated files and migration tooling; run broad final checks once unless a
  subsequent change or failure invalidates their evidence.

Organization-creation UI, new organization wiki/analytics workflows, document
moves/sharing, new scope widgets, tenant transfers, automatic allocation-conflict
resolution, live-operation cancellation and unrelated cleanups are out of scope.
Required existing UI and generated-client consumers are adapted. The restricted
newcomer/request/approval journey is included; organization creation and broader
organization administration UI remain deferred.

## Capabilities

### New Capabilities

- `corpus-authorization`: organization/team/project ownership, local roles,
  isolation, conversation-bound access, bounded authorization and offline cutover.

### Modified Capabilities

- `document-import-conflicts`: overwrite preserves identity and folder and cannot
  adopt a document from another folder or space.

## Impact

fred-core models and ReBAC; control-plane registry, users, membership, agents,
sessions and evaluation; Knowledge Flow corpus lifecycle/search and indexes;
SDK/runtime context and ReAct/Deep tools; generated APIs and frontend consumers;
Alembic, offline translation and operator documentation. Authentication remains
in the IdP; Fred/OpenFGA owns authorization.

This is the target for one major-release implementation PR, not a declaration
that these behaviors have shipped. Review the reconciled artifacts before code;
fresh-install, migrated-install and restore evidence are required before release.
