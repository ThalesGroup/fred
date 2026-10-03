## Purpose

Provide team and project collaboration spaces with uniform corpus permissions,
context-bound agent access and authorization work independent of corpus size.

## ADDED Requirements

### Requirement: Projects are explicit collaboration spaces

The system SHALL support creating and administering projects under teams in the
current organization. A project SHALL have one immutable parent team; its members
SHALL be team members with explicitly assigned project roles. Team membership or
team editor/analyst status SHALL NOT implicitly grant project access. The UI SHALL
distinguish project membership management from ordinary folder organization.

#### Scenario: Clara is outside Atlas

- **WHEN** Clara is a team member, editor or analyst but has no Atlas role
- **THEN** those roles alone do not reveal Atlas or its corpus and conversations

#### Scenario: A project is created

- **WHEN** an authorized team admin/editor creates Atlas and nominates its admins
- **THEN** Atlas has explicit parentage and membership, and creating it does not
  automatically grant its creator a project content role

### Requirement: Space permissions govern corpus access

The system SHALL authenticate through the existing IdP and authorize space
operations through ReBAC. All members SHALL read their space's corpus; corpus
mutation SHALL require that space's editing permission. Folders SHALL have no
independent grants, restrictions or cross-space sharing. Canonical ownership SHALL
be resolved server-side, never trusted from a caller or index.

#### Scenario: A confidentially named subfolder is created

- **WHEN** Atlas contains General and Confidential folders
- **THEN** every Atlas member can read both, and neither folder can override access

#### Scenario: Two teams want a common folder

- **WHEN** a folder belongs to one team
- **THEN** it cannot be shared with another team; organization-common resources,
  when exposed, are readable by all organization members, not selected teams

### Requirement: Corpus membership is exclusive

Every corpus document SHALL belong to one immutable folder in one owning space.
All writers SHALL enforce this invariant. Links and moves SHALL NOT be supported.
Session attachments SHALL retain their distinct owner/session isolation.

#### Scenario: A writer attempts reparenting

- **WHEN** import, overwrite or source sync supplies multiple/no folders or changes
  an existing document's folder or space
- **THEN** it is rejected before content or membership mutation

### Requirement: Editor and analyst authority is local and traceable

Project editing and analysis SHALL require the corresponding explicit project
roles. Project analysts SHALL be able to analyze project conversation history,
including history predating their appointment; derived datasets SHALL remain in
that project. Grants and removals SHALL record actor, subject, role, space and time.
Ordinary membership SHALL NOT make all members' conversations mutually visible.

#### Scenario: An analyst works across two projects

- **WHEN** Antoine has analyst roles in Atlas and Boreal but not a third project
- **THEN** he can analyze the first two histories independently, cannot inspect the
  third, and cannot publish either project's datasets into the team via that role

### Requirement: Conversations have an immutable execution space

Every conversation SHALL remain bound to its initial team or project. Team agents
SHALL be reusable in child projects without copying. Their reachable corpus SHALL
be determined by conversation space and user authorization, not agent authorship
or the user's membership in other projects. History, generated content and memory
SHALL NOT flow into another space when navigation changes.

#### Scenario: Alice uses a team agent in Atlas

- **WHEN** Alice belongs to Atlas and Boreal and starts a conversation in Atlas
- **THEN** the unrestricted agent can use Atlas and applicable ancestor-common
  resources, but cannot use Boreal; the same agent in team context sees no projects

#### Scenario: Alice switches to Boreal

- **WHEN** Alice changes the selected space in the UI
- **THEN** working in Boreal requires another conversation without Atlas history

#### Scenario: An agent belongs to Atlas

- **WHEN** a user tries to use the Atlas-owned agent in team or Boreal context
- **THEN** that agent is unavailable there, even if the user also belongs to Atlas

### Requirement: Document scope narrows contextual access

Folder selection SHALL include descendants. Agent restrictions SHALL remain binding
in every execution space; existing chat scope controls SHALL only narrow authorized
reach according to their supported mode. No selection SHALL mean the contextual
corpus subject to configured restrictions. An empty or invalid scope SHALL NOT
widen to global search. Existing direct-document selection SHALL remain supported.

#### Scenario: A team agent is fixed to Process documents

- **WHEN** that agent is used in Atlas
- **THEN** it remains restricted to Process documents and cannot read Atlas offers

#### Scenario: A selectable scope names Technique

- **WHEN** the agent permits chat selection and Alice selects Technique
- **THEN** retrieval includes its descendants but excludes Commercial

#### Scenario: A selected scope resolves to nothing

- **WHEN** a nonempty explicit selection resolves to zero permitted folders or
  documents after contextual and configured restrictions
- **THEN** the request returns no corpus results or an explicit scope error,
  never treating that result as an omitted selection authorizing the whole context

### Requirement: Authorization precedes retrieval and has a bounded cost

Corpus retrieval SHALL constrain its candidate universe to authorized contextual
spaces before ranking. For fixed context and operation, permission checks SHALL
NOT grow with folder/document counts. Discovery SHALL use finite pages and explicit
continuation; input and retry limits SHALL be enforced. Counts, content, citations
and agent tools SHALL obey the same boundary. Folder summaries and label enrichment
SHALL NOT enumerate contained document IDs or metadata.

#### Scenario: Atlas gains thousands of folders and documents

- **WHEN** the same scoped or unrestricted Atlas corpus request is repeated
- **THEN** space-authorization work remains within the same bound and no global
  document permission list or per-folder permission loop is required

#### Scenario: An index contains stale or misleading ownership

- **WHEN** a candidate has no canonical row or its ownership disagrees with the filter
- **THEN** its content and metadata are withheld regardless of the index label

### Requirement: Lifecycle and audit preserve the space boundary

Import/export SHALL preserve space ownership, roles and single document membership;
incompatible legacy archives SHALL be rejected. Retried ingestion and deletion
SHALL NOT expose orphan corpus content. Execution evidence SHALL identify the user,
space, agent/configuration, effective scope and sources. Project access removal
SHALL follow the same access-removal principle as team membership removal; detailed
revocation timing and active-session mechanisms are outside this change's decisions.

#### Scenario: An attachment or deleted hit is requested

- **WHEN** corpus permission exists but the requested item is a session attachment
  without session authority or a deleted canonical document
- **THEN** corpus access alone does not permit serving that item
