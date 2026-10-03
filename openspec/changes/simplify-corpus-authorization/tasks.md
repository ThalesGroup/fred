Implementation requires approval of the revised scope. This PR remains planning
only; the provisional admin policy must be resolved before its implementation.
All validation uses isolated fresh data; migration and Monday validation are separate.

## 1. Project and ownership foundations

- [ ] 1.1 Resolve the admin review gate and agree dependent PR boundaries before coding; verify approved permissions and one authoritative target (the RFC now delegates its project slice here).
- [ ] 1.2 Add explicit project/parent identities, membership and scoped ReBAC roles using existing services; verify creation/bootstrap, team-membership constraints and no implicit editor/analyst project access.
- [ ] 1.3 Provide project creation, membership/role management and navigation with generated clients and audit events; verify a team can create and administer Atlas without treating it as a folder.

## 2. Corpus conversion

- [ ] 2.1 Enforce space-owned folders and single document membership; remove corpus folder ACLs/document tuples and writers while preserving non-corpus policies; verify fresh schema, name conflicts and no per-folder grants.
- [ ] 2.2 Update ingestion/sync, overwrite, deletion, team quota accounting and clean import/export; verify reparenting rejection, round-trip space roles and no orphan access under retry/concurrency.
- [ ] 2.3 Gate metadata/content/vector/tabular/filesystem access by contextual spaces before retrieval; verify subtree scope, stale-index rejection, bounded calls and summary-only folder reads.

## 3. Conversation and consumer integration

- [ ] 3.1 Carry immutable team/project context through sessions, history, runtime grants, delegated tools and attachments; verify server-side ancestry, no context switching and no sibling access for multi-project users.
- [ ] 3.2 Enable team-agent reuse and project-owned agents with existing fixed/selectable scope controls; regenerate APIs and verify ReAct/Deep scoped and unscoped behavior without new picker variants.
- [ ] 3.3 Scope analyst history, datasets and generated content to their origin and expose effective context in UI/audit; verify retrospective analyst access, ordinary conversation privacy and no cross-space publication.

## 4. Validation and close-out

- [ ] 4.1 Validate fresh setup with real OpenFGA, 200 teams/2,000 members, multiple projects and increasing folder/document counts; record whole-turn and request check counts, transport attempts, rows read and latency against fixed-context bounds, plus agreed manual scenarios.
- [ ] 4.2 Complete documentation dispositions, root quality/migration checks and independent full-branch review; record evidence in the PR, then sync/archive shipped specs only after complete integration. Keep offline translation and detailed revocation design separately tracked.
