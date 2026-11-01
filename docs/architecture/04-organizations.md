# 4. Organizations and spaces

An **organization** brings together people and their working spaces. **Teams**
support shared work; **projects** organize work within a team. A **personal space**
is dedicated to one person while remaining under the organization's governance.
It is a distinct kind of space, not a collective team.

## Institutional governance and business work

The organization is both an institutional boundary and a shared business workspace.
Its owner manages the community and common resources, such as an organization corpus
or assistant, with analysts, editors and members. Teams and projects use these
resources under their access rules.

The organization admin names and replaces organization owners and reads supervision
aggregates, without content access or business-structure authority. The organization
owner creates teams; the team owner creates projects, naming their initial owner.
The [roles annex](A11-roles.md) details the mandate and the organization access allowlist
that remains unimplemented.

## Spaces and memberships

```mermaid
flowchart TB
    organization["Organization"] --> team["Team"]
    team --> project["Project"]
    organization -. "Governance only" .-> personal["Personal space"]

    classDef default fill:#F1F5F9,stroke:#64748B,color:#0F172A
```

Each team belongs to one organization, and each project to one team. People see
and use these spaces according to roles held directly on each space. The hierarchy
grants no child-space rights; see [Security](03-security.md).
Folders organize documents within a space; they do not create another access boundary.

## One person, one organization

One Fred installation can host several organizations. A person is attached to
**at most one organization** and may participate in several of its teams and
projects. Signing in does not create that attachment. Platform administration
roles are separate from organization membership.

The UI shows the organization in Profile and lets the user choose accessible
working spaces. It does not offer an organization switcher.

## Personal spaces

An entitled user opens Personal space to create it once; later openings reuse it.
It has no projects, accepts no additional members and inherits no content rights
from the organization or teams. The organization can revoke the user's access.
Creating an account or organization does not automatically create a personal space.

## Organization supervision

In the current implementation, the organization admin opens **Organization
supervision** from Administration. This aggregate visibility is recorded as a
[mandate question](A11-roles.md#responsibility-boundaries-and-current-enforcement).
The summary covers documents, processing, published results and direct role counts,
without exposing content or personal identities. Selecting a team opens its detail
in a side panel; Refresh reloads the summary and the open detail.

```mermaid
flowchart TB
    owner["Organization admin"] --> summary["Organization summary"]
    summary --> direct["Organization's<br/>own resources"]
    summary --> teams["Teams and<br/>their projects"]
    summary --> personal["Personal spaces<br/>combined"]

    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class owner,summary,direct,teams,personal neutral
```

Team details include their projects. Organization totals cover all teams,
regardless of the page consulted. Retired documents awaiting purge are counted
separately. Published counts describe recorded results, not live storage health.

## Platform organization owneristration

A platform admin creates an organization and appoints its owner and admin.
Those responsibilities do not automatically grant access to documents. Provisioning
can also import accounts, teams, projects and explicit roles together; the
[user journey](02.1-user-journeys.md) illustrates this setup.

The current API also lets a platform admin retire a space and its descendants,
beyond the agreed limited platform-admin remit: access closes first,
then cleanup follows. A scope containing documents cannot be retired through this
operation. User accounts are retained.

The [technical annex](A8-organizations.md) details membership rules, provisioning,
placement and cleanup contracts, with links to implementation references.
