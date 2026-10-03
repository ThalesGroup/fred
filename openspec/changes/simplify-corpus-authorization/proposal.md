## Why

Corpus authorization currently duplicates membership and performs work proportional
to document counts. The correct boundary is the owning collaboration space, not
an individual folder: teams and projects hold rights; folders organize documents
and narrow searches. Introduce usable projects now to avoid a temporary folder-ACL
architecture that must later be replaced.

Tracking: [#2938](https://github.com/ThalesGroup/fred/issues/2938);
organization/project context: [#2921](https://github.com/ThalesGroup/fred/issues/2921).

## What Changes

- **BREAKING**: corpus folders have one owning space and no independent grants,
  restrictions or cross-space sharing. Each document has one immutable folder.
- Introduce projects under teams in the existing single organization: explicit
  membership, scoped roles, project administration and a usable project context.
- Keep authentication in the IdP and authorization in ReBAC. Team editor/analyst
  roles grant no implicit access to projects; equivalent project roles are explicit.
- Bind each conversation permanently to its team or project. Reuse team agents
  in projects; intersect contextual access with configured and supported chat scope.
- Authorize spaces before corpus retrieval; remove document authorization lists
  and corpus folder/document ACL duplication. Folder selection includes descendants.
- Keep project conversations, evaluation datasets and generated content in their
  originating space. Audit role changes and effective execution context.
- Align corpus writers, reads, generated clients and UI; validate from scratch
  and consolidate documentation around one target contract.

Multiple-organization administration, offline data translation/rollout, new scope
widget variants, detailed revocation mechanisms, graph checkpoints and unidentified
MCP removals are excluded. This is not the Monday validation branch. Cross-project
admin governance access remains a team-review assumption, not a settled permission.

## Capabilities

### New Capabilities

- `corpus-authorization`: team/project ownership and roles, conversation-bound
  corpus access, immutable document membership and bounded authorization work.

### Modified Capabilities

- `document-import-conflicts`: overwrite preserves identity and folder and cannot
  adopt a document from another folder or space.

## Impact

fred-core ReBAC and membership models; control-plane project management, sessions,
agent ownership and evaluation; Knowledge Flow corpus lifecycle/search;
runtime context and ReAct/Deep tools; frontend space navigation and generated APIs.
The project slice refines the existing organizations/projects RFC; multi-tenant
onboarding and administration remain separate. This PR contains planning only.
