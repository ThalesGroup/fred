# 2. Journeys

Journeys follow concrete scenarios to explain how Fred's architectural rules
work together. Each journey has its own subchapter and links to the relevant
domain chapters for the underlying rules.

| Subchapter | Reader's question |
| --- | --- |
| [2.1. User journeys](02.1-user-journeys.md) | How does a user go from first login to creating a folder? |
| [2.2. Document journey](02.2-document-journey.md) | How does a user import a PDF, follow processing and read the result? |
| [2.3. Models and first chat](02.3-agent-administration.md) | How does Alice authorize models for Acme, and how does Bob get answers, including from Research's documents? |

Follow chapter 2.3 from the organization's model choices to Bob's first exchange.
Each journey explains its own scope; a conversation does not imply document search
or use of external tools.

## Example people and spaces

The following fictional people and spaces keep examples consistent. Acme contains
Research; Globex contains Support. Each person belongs to only one organization.
Names identify the examples; permissions come from explicit role grants.

The [roles annex](A11-roles.md) defines the responsibilities and current permissions
behind these examples.

| Function | Acme | Globex | Direct role at that scope |
| --- | --- | --- | --- |
| Organization admin | **Oscar** (`oscar`) | **Olivia** (`olivia`) | `organization_admin` on the organization |
| Organization owner | **Alice** (`alice`) | **Grace** (`grace`) | `owner` on the organization |
| Team | **Research** | **Support** | - |
| Team owner | **Carl** (`carl`) | **Marc** (`marc`) | `owner` on the team |
| Team analyst | **Elena** (`elena`) | **Nadia** (`nadia`) | `analyst` on the team |
| Team member | **Carol** (`carol`) | **Phil** (`phil`) | `member` on the team |
| Team editor | **Bob** (`bob`) | **Zoe** (`zoe`) | `editor` on the team |
| Organization and team reader | **Léa** (`lea`) | - | `member` on Acme and on Research |

Each of the four paired team personas also holds `member` directly on their organization,
the prerequisite for a team role. This parent role grants organization-level read
access but does not descend into teams. Organization admins and owners
hold only their listed roles; none of these thirteen people holds a
platform role. Carl can administer Research without reading its documents; Bob
can read and contribute; Carol and Elena can read. Member stays local, whereas
analyst also reaches descendant projects when a scenario introduces one.

Léa illustrates read access across Acme and Research through two explicit `member`
grants. These grant neither editing nor administration, and no access to Globex
or to other people's personal spaces and private conversations.

The demo bundle supplies these thirteen organization accounts and two teams. The
platform account is bootstrapped separately. Additional projects and role combinations
are stated explicitly in the relevant examples; the bundle creates no projects or
personal spaces.
