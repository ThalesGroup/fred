## Purpose

Provide organization, team and project ownership with local roles, isolated
conversation contexts and corpus authorization independent of document count,
delivered through one offline major-version cutover.

## ADDED Requirements

### Requirement: Ownership has one explicit organization boundary

Each admitted user SHALL belong to exactly one organization, at least one
collaborative team in it, and one owner-only personal team in it. Organization
assignment SHALL be explicit rather than inferred from first join or IdP roles.
Each collaborative team SHALL have one immutable organization parent; each project
SHALL have one immutable collaborative-team parent. Canonical SQL SHALL own this
structure with typed, constrained references. No project SHALL belong to a personal
team. Ordinary discovery and membership operations SHALL respect this boundary.

#### Scenario: A person belongs to several teams
- **WHEN** Alice belongs to two collaborative teams in the same organization
- **THEN** both memberships coexist with one organization assignment and one personal team

#### Scenario: A foreign organization is named
- **WHEN** a caller requests another organization's team, project or corpus by ID
- **THEN** ordinary membership/content permissions do not authorize access

#### Scenario: Invalid parentage is written
- **WHEN** a project is assigned an organization directly or a personal-team parent
- **THEN** the invalid structure is rejected

### Requirement: Newcomer admission shares the team membership flow

An authenticated person without organization membership SHALL be able to request
admission through a restricted onboarding surface. An active local organization
admin SHALL approve or reject the request. The request lifecycle, admission code
and interaction pattern SHALL be shared with team membership rather than duplicated
for organizations. Request state SHALL NOT itself confer a role.

This version SHALL also support requests to closed collaborative teams, using the
same request representation and decision path. Only a member of the team's own
organization SHALL request admission, and only an active local team admin SHALL
decide it. Approval SHALL grant member only. Existing direct local-admin admission
SHALL remain available. Requests SHALL NOT apply to projects or personal teams.

Successful admission SHALL establish exactly one organization, ordinary membership
of an explicitly designated open welcome team in it, and one owner-only personal
team. Pending, rejected or incomplete admission SHALL NOT authorize corpus, agents,
conversations or personal workspace use. Organization approval SHALL NOT bypass
local administration of closed teams. Existing open-team joining SHALL remain
immediate.

#### Scenario: An unknown organization at first sign-in
- **WHEN** Alice authenticates without an organization assignment
- **THEN** she can request organization admission but cannot use any workspace
- **AND** her identity does not silently select an organization or create a personal team

#### Scenario: Organization admission succeeds
- **WHEN** the requested organization's active admin approves Alice's admission
- **THEN** Alice becomes its member and an ordinary member of its open welcome team, with one personal team
- **AND** she receives no editor, analyst or admin role from that approval

#### Scenario: Two organizations approve the same newcomer
- **WHEN** a second organization's approval attempts to admit an already admitted Alice
- **THEN** it is refused without granting roles or moving her existing organization, teams or personal space

#### Scenario: A member requests admission to a closed team
- **WHEN** Alice requests a closed collaborative team in her organization
- **THEN** its active local admin can approve or reject the request through the shared decision flow
- **AND** the pending request grants no team access and approval grants member only

#### Scenario: A parent admin attempts to approve a team request
- **WHEN** an organization admin without local team admin tries to approve Alice's request to that closed team
- **THEN** the decision is denied without granting membership

### Requirement: Four cumulative roles remain local

Organization, team and project SHALL support member, editor, analyst and admin.
Elevated roles SHALL include local member rights; combinations SHALL be explicit.
Members SHALL read local common corpus and use available agents; editors SHALL
manage local corpus/agents; analysts SHALL access the supported local conversation
analysis and evaluation data; admins SHALL govern local membership. Admin alone
SHALL NOT substitute for editor or analyst. Organization analyst SHALL NOT grant
descendant analysis, and its presence SHALL NOT introduce a new organization
analytics or conversation workflow.

#### Scenario: A local administrator edits or evaluates
- **WHEN** an admin has neither editor nor analyst
- **THEN** the admin can read local corpus and manage membership but cannot use content-editing or analyst-only evaluation operations

#### Scenario: One administrator runs a small team
- **WHEN** the sole local admin explicitly grants themselves editor or analyst
- **THEN** the audited grant is allowed without requiring a second admin

### Requirement: Governance does not admit an outsider to a closed space

Organization admin SHALL govern team structure and team admin SHALL govern project
structure without implicit descendant content access. Admission or administrator
nomination in an existing closed space SHALL require an active local admin.
An outside parent admin SHALL NOT grant themselves membership or administration
there. Role mutations SHALL record actor, subject, role, space and time.
Existing pending team-admin charter nominations SHALL remain non-administrative.

#### Scenario: Claire administers the parent only
- **WHEN** Claire attempts to read a closed descendant's corpus or grant herself a local role
- **THEN** both operations are denied while authorized structural governance remains available

#### Scenario: A local admin admits Claire
- **WHEN** the closed space's active local admin assigns Claire member
- **THEN** Claire gains its member permissions without gaining analyst or editor

### Requirement: Project bootstrap is restricted to team administrators

Only team admin SHALL create a project and nominate its first administrator from
the team's members. The creator MAY nominate themselves at creation; otherwise
creation SHALL NOT grant them a local project role. Bootstrap SHALL NOT serve as
an administrator-replacement path on an existing project.

#### Scenario: A team editor tries to create a project
- **WHEN** an editor without team admin requests project creation
- **THEN** creation is denied

#### Scenario: A creator nominates themselves
- **WHEN** a team admin creates Atlas and names themselves its first admin
- **THEN** Atlas is created with explicit parentage and the creator's explicit local role

### Requirement: Open teams remain joinable inside their organization

A team's existing open-joining policy SHALL permit same-organization users to
join as ordinary members, including users who also hold parent administrative
roles. Closed teams and projects SHALL retain explicit admission. Public team
visibility SHALL NOT grant corpus access or cross-organization discovery.

#### Scenario: Alice joins an open team
- **WHEN** Alice joins an open team in her organization
- **THEN** she receives member only, with no editor, analyst or admin role

#### Scenario: Alice requests an open team in another organization
- **WHEN** Alice supplies that team's ID to the join endpoint
- **THEN** the request is denied despite its open-joining policy

### Requirement: Project access depends on parent-team membership

Project members SHALL be members of its parent team. Team removal SHALL revoke
effective access to all its projects and remove their stored project roles.
Removing one project membership SHALL leave other memberships intact. Direct
project grants remaining during cleanup SHALL NOT authorize a removed team member.
Active users SHALL retain at least one collaborative team; losing the last one
requires explicit reassignment or the existing account-removal lifecycle.

#### Scenario: Alice leaves a project's parent team
- **WHEN** her team removal succeeds while a project tuple remains pending cleanup
- **THEN** her next protected request to that project is denied

#### Scenario: Alice leaves only Atlas
- **WHEN** her Atlas membership is removed
- **THEN** her parent-team and Boreal memberships remain unchanged

### Requirement: Personal content is private with one-way common-resource access

A personal space SHALL remain an owner-only team with no projects. Its owner MAY
read organization-common corpus and use organization agents within it. Personal
documents, conversations, memory and outputs SHALL NOT become accessible to
collaborative teams or administrators through their roles. Collaborative-team
content SHALL NOT enter a personal conversation merely because the owner belongs
to those teams.

#### Scenario: A personal conversation uses a common agent
- **WHEN** Alice uses an organization agent in her personal space
- **THEN** it can use her private and organization-common corpus, but neither its author nor organization admins gain access to her conversation

### Requirement: Spaces own corpus permissions

All corpus folders SHALL have one owning space. Folder hierarchy SHALL remain
inside that space and SHALL confer no independent grants, restrictions or
cross-space sharing. Organization-common corpus SHALL be readable by its
organization's members; mutation SHALL require editor at the owning level.
Authorization SHALL use canonical server-side ownership, never a caller or index
label alone. Corpus folder/document ACL relations SHALL be removed from FGA.

#### Scenario: Atlas contains a Confidential folder
- **WHEN** an Atlas member reads its corpus
- **THEN** the folder name does not restrict or expand that member's permissions

#### Scenario: A project editor reads an organization procedure
- **WHEN** the editor reads the inherited procedure and then attempts to overwrite it
- **THEN** reading is allowed but mutation requires organization editor

### Requirement: Corpus membership is exclusive

Every corpus document SHALL have exactly one immutable folder in one owning
space. Writers SHALL reject multi-folder, unfiled or reparenting input before
mutation, including source synchronization. Same-folder name uniqueness SHALL be
enforced transactionally. This change SHALL NOT add document movement or sharing.
Session attachments, including tabular attachment metadata, SHALL retain their
distinct session/owner isolation without becoming unfiled corpus documents.

#### Scenario: A writer changes a document's destination
- **WHEN** an import, overwrite or sync changes an existing document's folder or space
- **THEN** it is rejected without changing its content or ownership

#### Scenario: An Excel attachment has no corpus folder
- **WHEN** a valid conversation attachment is ingested
- **THEN** its session-owned processing remains supported without creating corpus membership

### Requirement: Conversations have an immutable execution space

Every conversation SHALL remain bound to its initial collaborative team, project
or personal team. Agents SHALL have a separate owning space. Organization agents
SHALL be usable in their organization's descendant spaces; collaborative-team
agents in their own team and child projects; project and personal agents locally.
Context SHALL be server-validated through session/history, execution/delegation,
tools and evaluation. Agent authorship SHALL grant no conversation access.

#### Scenario: A team agent serves Atlas
- **WHEN** Alice uses the same team agent in Atlas and Boreal
- **THEN** each conversation retains its own project context without copying the agent

#### Scenario: Alice switches spaces
- **WHEN** Alice navigates from Atlas to Boreal
- **THEN** working in Boreal requires another conversation; Atlas history and outputs are not transferred

### Requirement: Corpus reach follows the conversation and only narrows

A project conversation SHALL reach that project and its parent-team and
organization-common corpus. A team conversation SHALL reach team and organization
common corpus, excluding projects even when the user belongs to them. Personal
reach SHALL follow its private/common rule. Applicable existing platform-common
resources SHALL retain their supported policy.
Agent restrictions and supported chat scope controls SHALL only narrow that
envelope. Folder selection SHALL include descendants. No selection SHALL mean the
contextual envelope subject to configuration; an explicit empty or invalid
intersection SHALL NOT widen to global search. Existing document selection SHALL
remain supported without new widget variants.

#### Scenario: Alice belongs to Atlas and Boreal
- **WHEN** an unrestricted agent searches from Atlas
- **THEN** Boreal is excluded even though Alice could access it in another conversation

#### Scenario: A team agent is fixed to Process documents
- **WHEN** that agent serves Atlas
- **THEN** its scope remains Process documents, not all Atlas documents

#### Scenario: A selected scope resolves to nothing
- **WHEN** a nonempty explicit selection has no permitted intersection
- **THEN** no corpus results or an explicit scope error is returned, never global search

### Requirement: Analyst data stays in its execution space

Reading other members' conversations for analysis and managing their derived
evaluation datasets SHALL require explicit local analyst. Local analysts MAY
analyze history predating their appointment. Ordinary membership SHALL NOT expose
other members' conversations. Memory, outputs and derived datasets SHALL remain
in their execution space; parent or inherited-agent authorship SHALL NOT publish
them upward.

#### Scenario: Antoine analyzes two projects
- **WHEN** Antoine is analyst in Atlas and Boreal but not a third project
- **THEN** he can analyze their histories independently and cannot read the third or publish their datasets into the team through those roles

### Requirement: Authorization precedes retrieval and has bounded cost

For fixed context and operation, corpus permission work SHALL NOT grow with
document count, folder count or folder depth. Candidate SQL/vector/tabular
retrieval SHALL be constrained before ranking. Direct content, metadata, counts,
citations, service identities and agent tools SHALL enforce the same boundary.
Folder summaries SHALL NOT enumerate contained document IDs or metadata.
Discovery SHALL use finite pages and explicit continuation; inputs and transport
attempts SHALL be bounded. Canonical membership checks SHALL reject stale index
hits in batches without per-document permission checks.

#### Scenario: Atlas grows by thousands of documents and folders
- **WHEN** the same contextual corpus request runs before and after growth
- **THEN** logical space checks and transport attempts remain within the same bound without global document permission lists

#### Scenario: A stale index mislabels ownership
- **WHEN** a hit's canonical row is missing or disagrees with the authorized context
- **THEN** its content and metadata are withheld

### Requirement: Revocation applies to the next protected request

After an access removal succeeds, the next protected request SHALL evaluate the
updated authorization, including requests made from existing conversations.
Positive authorization decisions SHALL NOT be reused across requests so as to
delay revocation. Already-authorized in-flight work MAY finish; subsequent tool
requests SHALL reauthorize. Remote cancellation of in-flight work is not required.

#### Scenario: An open conversation makes another tool request
- **WHEN** its user's space membership was successfully revoked after the previous call
- **THEN** the next protected call is denied even though the conversation remains open

### Requirement: Corpus lifecycle preserves canonical ownership

Overwrite, ingestion retries, deletion and import/export SHALL preserve canonical
space ownership, identity and local role semantics. Deleted/orphaned corpus rows
SHALL NOT remain readable through stale index entries. Existing synchronized-source
write restrictions SHALL remain enforced. A project's documents SHALL be charged
once to the parent team's quota, not again for inherited reads.

#### Scenario: An inherited document is read from two projects
- **WHEN** both projects use a document in their parent team's common corpus
- **THEN** reading does not duplicate the document or its storage charge

### Requirement: Offline cutover replaces the old runtime model

The major release SHALL include a separate offline tool accepting organization
definitions, team allocation and initial organization role assignments. It SHALL
preserve supported existing identities, team memberships and corpus access, attach
personal teams to their owners' organizations, and create no projects. Coherent
team allocation is an operator precondition; automatic conflict resolution is
not required. Source ownership and legacy grants SHALL be checked for target
representability before conversion; unsupported ownership or exceptional ACLs
SHALL be reported rather than silently changed. The agreed explicit-analyst behavior SHALL be declared as a compatibility
change, without silently creating analyst grants.

The platform's writers SHALL be stopped during translation of PostgreSQL, FGA
and required index metadata. The new runtime SHALL contain no old-model feature
switch, dual read/write or startup translation fallback. Fresh installation and
migrated installation SHALL use the same target model. Organization creation SHALL
be available through installation/migration tooling; its UI is deferred.

#### Scenario: Existing teams are allocated to several organizations
- **WHEN** the offline tool runs with a coherent explicit mapping
- **THEN** each team and personal space has its intended organization, existing IDs remain stable and there are zero projects

#### Scenario: Old rows cannot satisfy the target ownership rules
- **WHEN** a source corpus document has unsupported ambiguous or multiple folder ownership
- **THEN** translation reports the unsupported input and does not invent a project, duplicate account or silently broaden access

#### Scenario: A personal folder has a legacy grant to another user
- **WHEN** preflight finds a personal folder whose viewer/editor grant cannot be represented by the target owner-only personal space
- **THEN** conversion is refused before mutation, identifying the unsupported grant without silently dropping it or admitting another person to the personal space

### Requirement: Cutover has a verified restoration path

Release acceptance SHALL include migration and restoration on an isolated
representative copy. Backup SHALL cover the affected SQL databases, FGA model
and tuples, relevant files/index state and old binaries/configuration. Restore
SHALL return the stopped platform to that coordinated pre-cutover snapshot.
Application export alone SHALL NOT be treated as a complete backup. Operator
documentation SHALL state that rollback does not preserve post-reopening writes.

#### Scenario: Cutover validation fails
- **WHEN** operators choose rollback before admitting users to the new version
- **THEN** the documented restore returns the previous version with its matching data and authorization state
