## ADDED Requirements

### Requirement: Who can read analytics

Platform observers and administrators SHALL read every tab, every analytics
read and the export, for the whole platform or any set of non-personal teams.
A team admin SHALL read them for teams they administer only. Anyone else SHALL
be refused as forbidden.

#### Scenario: Team admin reads their team

- **GIVEN** a user who is team admin of team A only
- **WHEN** they request analytics scoped to team A, then to teams A and B
- **THEN** team A's figures are returned, and the second request is forbidden

#### Scenario: Team editor reads their team

- **GIVEN** a member, editor or analyst of team A who is not its team admin
- **WHEN** they request analytics scoped to team A
- **THEN** the request is forbidden

### Requirement: No content or identity

Analytics reads and the export SHALL return only aggregates and names of
teams, agents, capabilities, skills and models, never message content,
conversation titles, user names, emails or ids.

#### Scenario: Export

- **WHEN** an administrator exports the platform analytics
- **THEN** no sheet contains a user name, email, user id or message text

### Requirement: Indicator definitions

A visitor SHALL be a user with an authenticated API request in the period; an
active user, a user with a completed agent turn; a new user, a user whose
first recorded event falls in the period; people with access, the users the
access rule admits plus the whitelist (all known users without restriction),
or a team's current members.

#### Scenario: Visitor who never writes

- **GIVEN** a user with API requests but no message in the period
- **WHEN** the adoption funnel is read
- **THEN** the user is a visitor and not an active user

### Requirement: Team scope

Every read and the export SHALL accept the whole platform or a set of teams.
A figure whose data has no team SHALL NOT be returned for a team scope, rather
than returning a platform-wide value.

#### Scenario: Platform-only figure under a team scope

- **WHEN** the teams section is read for team A
- **THEN** the team vs personal conversation split is `null`

### Requirement: Period and comparison

The page SHALL offer rolling periods (7 days, 30 days, 3 months, 12 months),
calendar shortcuts, a custom range and previous/next navigation, and SHALL show
each headline figure against the same-length period just before.

#### Scenario: Rolling three months

- **GIVEN** today is 27 October 2026
- **WHEN** "3 months" is selected
- **THEN** the period runs from 27 July 2026 at the current time to now

### Requirement: Costs in euros

Estimated costs SHALL be shown and exported in euros, converted from the USD
model prices with a rate set next to them (default 1 EUR = 1.12 USD).

#### Scenario: Default rate

- **WHEN** a cost of 112 USD is displayed
- **THEN** it reads 100 euros

### Requirement: Excel export

The export SHALL produce `analytics_<scope>_<start>_<end>.xlsx` for the current
scope, period and filter, with typed values, the indicator explanations, and
no chart.

#### Scenario: Two-team export

- **WHEN** an observer exports two teams for 2026-09-26 to 2026-10-25
- **THEN** the file name carries the scope and both dates
- **AND** the Summary sheet lists each indicator with its current and previous value

### Requirement: Capability usage

The capability table SHALL show per capability the agents equipped, the agents
that used it, tool calls, users reached and the failure share. Tool calls
recorded without a capability SHALL NOT be counted.

#### Scenario: Old tool calls

- **WHEN** tool calls carry no capability id
- **THEN** they are counted in no row

### Requirement: Web research hidden when disabled

When web research is enabled for no team and no personal space, no page or
export SHALL show anything about it.

#### Scenario: Disabled platform-wide

- **WHEN** an observer opens the Technical tab
- **THEN** no web research section is shown

### Requirement: Team usage page

A team admin SHALL see the platform views limited to their team, without the
Technical tab, the scope selector or cross-team figures, and named Analytics.
Other members SHALL see only their personal usage, named My usage.

#### Scenario: Team member

- **GIVEN** a member of team A who is not its team admin
- **WHEN** they open the usage page of team A
- **THEN** only their personal usage is shown and no team analytics is requested

### Requirement: User attribute filter

The platform page SHALL let an observer restrict every figure and the export to
users whose stored platform-access attributes match conditions built like an
access rule, and SHALL show how many users match and how many have no stored
value. Figures from configuration SHALL say they are not filtered. A filter
matching more than 50 000 users SHALL be refused.

#### Scenario: Organisation filter

- **GIVEN** U1 and U2 have `organisation = A`, U3 has `B`, U4 has no value
- **WHEN** an observer applies `organisation equals A`
- **THEN** the page shows 2 users matching and 1 without data
- **AND** activity figures count only U1 and U2

#### Scenario: Team admin sends a filter

- **WHEN** a team admin who is not an observer sends a user filter
- **THEN** the request is forbidden
