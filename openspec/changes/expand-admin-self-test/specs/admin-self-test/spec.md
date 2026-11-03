## ADDED Requirements

### Requirement: Checks are grouped into families

The self-test page SHALL present its checks as families, in this order:
platform, identity, knowledge, agents, prompts, conversations, teams, web
research, security, observability and authorization. Each family SHALL have its own
action and step report. The page SHALL run one family at a time. Every check
SHALL run as the signed-in admin and SHALL ask for no password, except the
existing "test another profile" probe.

#### Scenario: A family is running

- **WHEN** one family is running
- **THEN** every other action on the page is unavailable until it finishes

### Requirement: Run all

The page SHALL offer one action that runs every family in order, excluding the
credential-expiry check, and SHALL offer one combined report covering every
family run so far, with the date and the page origin.

#### Scenario: One family fails

- **WHEN** a family reports a failed step during Run all
- **THEN** the remaining families still run, and the combined report shows the failure

### Requirement: Run-scoped fixtures

Every object a family creates SHALL carry the run token in its name. Teardown
SHALL delete only the identifiers the run created, SHALL run however the
family ends, and SHALL verify that what it deleted is gone. A family SHALL NOT
write shared platform settings: platform prompt, model bindings, UI settings,
announcements or theme.

#### Scenario: A step fails mid-family

- **WHEN** a step fails after fixtures were created
- **THEN** the remaining steps report, and teardown still deletes those fixtures

### Requirement: Platform family

The platform family SHALL check, without writing anything: control-plane and
knowledge-flow health and readiness; that the account-status check answers;
that the token issuer matches the public provider configuration; browser,
token and server clocks; that every agent runtime serves at least one
available template; that the harness agent is available; that at least one
chat model profile is offered; and that capabilities, model bindings,
knowledge base definitions, UI settings, announcements and the purge policy can
be read.

#### Scenario: A runtime is down

- **WHEN** every template of one runtime is unavailable
- **THEN** the runtime step fails, naming that runtime

### Requirement: Authorization family

Beyond the existing single-account probe, the authorization family SHALL check
that protected routes of every backend refuse a missing, malformed or
re-signed token with 401; that platform-administration routes answer the
admin as its own platform roles say; and that, for teams the admin does not
belong to, team content routes are refused with 403 or 404.
The family SHALL explain why these checks matter, what Run all covers with the
current account, and why the two-account and session-expiry checks run
separately.

#### Scenario: Authorization appears last

- **WHEN** the admin opens the self-test page or runs all families
- **THEN** authorization is the final family in the page and combined report
- **THEN** its notice explains the checks and the separate actions

#### Scenario: A protected route answers without a token

- **WHEN** a protected route returns anything but 401 without a token
- **THEN** the step fails, naming the route and the status

#### Scenario: A valid token receives an unrelated error

- **WHEN** an admin or team-content route responds with 401 or a server error
- **THEN** the check fails rather than treating the response as permission denial

#### Scenario: The authorization write probe creates a prompt

- **WHEN** the temporary prompt is deleted after the write check
- **THEN** the test reads it again and reports failure unless it responds 404

#### Scenario: A second account is tested

- **WHEN** the deployment uses Keycloak
- **THEN** the admin can enter the test account and password for the automatic role campaign
- **WHEN** the deployment uses another OIDC provider
- **THEN** the admin can paste a short-lived API access token obtained through a separate sign-in
- **THEN** the token is discarded after the run and never appears in the report

#### Scenario: The supplied token belongs to the admin

- **WHEN** both tokens resolve to the same `current_user.id` in frontend bootstrap
- **THEN** the second-account probe fails before claiming isolation

#### Scenario: Two personal spaces are isolated

- **WHEN** two different accounts provide valid API access tokens
- **THEN** each account's team list includes its own personal team as a member and omits the other account's personal team
- **THEN** each account can read its own personal team, prompts, prompt context, prompt categories, prompt commands, agent templates, conversations and agents
- **THEN** each account receives 403 or 404 for the other account's corresponding routes
- **THEN** a temporary prompt created in the current admin's personal space is readable by its owner and refused to the other account by its exact URL
- **THEN** the test account creating a prompt in the admin's personal space is refused with 403 or 404
- **THEN** the probe verifies any temporary prompt against its run-specific name and content before attempting cleanup, even when a request fails
- **THEN** each successful deletion is confirmed by an owner read returning 404, and any fixture that cannot be safely identified or removed is reported

#### Scenario: The two accounts have different collaborative teams

- **WHEN** an account belongs to a collaborative team that the other account does not belong to
- **THEN** the team member can read that team's metadata
- **THEN** the other account receives 403 or 404 for the team's member-only content routes
- **THEN** the campaign creates its own disposable teams, without requiring an existing team selection


### Requirement: Knowledge family

The knowledge family SHALL work in the admin's personal space and SHALL check:
retrieval scoped to one folder and isolation from another through a real agent
turn; direct search under each search policy; ingestion and retrieval of one
small document per format the default ingestion profile processes as text:
plain text, Markdown, JSON Lines, PDF, Word, Excel and PowerPoint; a SQL query
on a CSV; that linking a document into a second folder makes it retrievable there
and unlinking removes it; that a non-retrievable document is not returned; the
folder's document tree; that deleting a folder leaves no retrievable chunk of
its documents; and, as an optional step, the corpus audit.

#### Scenario: A format cannot be extracted

- **WHEN** the deployment cannot ingest one of the formats
- **THEN** that format's step fails and the other formats still run

### Requirement: Agents family

The agents family SHALL check, with the harness agent in the personal space:
system-prompt delivery; that the agent's chat model resolves and is usable;
that an updated system prompt is delivered on every one
of several following turns; that a disabled instance cannot run and runs again
once enabled; that copy targets include the personal space; that a duplicate
under a chosen name is created and a second one under the same name is
refused; and that concurrent turns in separate sessions each receive only
their own session's context.

#### Scenario: Concurrent turns cross

- **WHEN** a turn's answer contains another session's marker
- **THEN** the step fails, naming both sessions

### Requirement: Prompts and conversations families

The prompts family SHALL check delivery of a context prompt, delivery of its
updated text, prompt categories, favorites, prompt commands, the marketplace
listing, and that a deleted prompt can no longer be read. The conversations
family SHALL check that a turn runs in its conversation, session listing,
rename, that an attachment is retrievable in its own conversation and never
from another one of the same person, attachment deletion, the inactive
conversations list, and bulk deletion.

#### Scenario: A deleted prompt is still readable

- **WHEN** reading a prompt after its deletion succeeds
- **THEN** the step fails

#### Scenario: A deleted fixture returns a server error

- **WHEN** a read after deletion responds with a server error
- **THEN** the test reports failure rather than counting the fixture as gone

### Requirement: Teams family

The teams family SHALL be skipped, with the reason, when the admin has not
accepted the team-admin charter, and SHALL NOT accept it. Otherwise it SHALL
create a disposable team administered by the admin and check: the admin's
permissions; granting and revoking the editor role, with a write refused while
revoked; a team prompt, folder and agent; the wiki when enabled; the join link;
the team's model routing; copying the team agent to the personal space; and
that deleting the team leaves none of its prompts, folders or agents
reachable.

#### Scenario: The charter is not accepted

- **WHEN** the admin has no recorded charter acceptance
- **THEN** the family is skipped and no team is created

### Requirement: Security and observability families

The security family SHALL report which response-hardening headers the page
origin sets, as an optional step, SHALL fail on plain HTTP outside a local address and on
error bodies that expose a stack trace, and SHALL fail when an uploaded SVG
document is served inline as SVG or HTML without a sandboxing policy. The
observability family SHALL check that usage KPI presets can be read, and SHALL
skip the search and metrics backends when the deployment does not provide them.

#### Scenario: An uploaded SVG is served inline

- **WHEN** the streamed preview of an uploaded SVG comes back inline as `image/svg+xml` with no `sandbox` policy
- **THEN** the step fails, because the document would run on the platform origin

### Requirement: Automatic role campaign with restoration

The optional two-account campaign SHALL require explicit confirmation, distinct
API-resolved identities and a bootstrap-root caller. It SHALL snapshot and
restore the target's direct platform roles, never changing the caller's roles.
It SHALL test six platform profiles (none and each role alone) and six team profiles per
visibility (nonmember, member, editor, analyst, charter-resolved administrator,
and administrator/editor/analyst union). It SHALL perform at most 150 actual checks, not an exhaustive matrix hidden
behind grouped report rows.
The complete campaign SHALL contain at most 150 actual checks including
transport, recovery and interruption. The second-account interface SHALL expose
only this campaign and credentials, without manual expected-role/team inputs.
It SHALL include personal-team discovery, personal catalog and exact prompt
isolation, additional platform role routes and member/session/agent team reads.
Personal fixture writes SHALL be limited to the current admin's space so
recovery never requires the second account credential.
Access expectations SHALL be independent of API permission projections.

#### Scenario: All roles and revocation
- **WHEN** the root launches the campaign with a dedicated second account
- **THEN** real platform reads, team reads/writes, role projections, cross-team
  and personal-space isolation are checked with the required role sets
- **AND** removing roles closes previously permitted accesses
- **AND** all run teams are deleted and original grants verified after teardown.

#### Scenario: Interrupted campaign
- **WHEN** execution fails, credentials expire or the page closes
- **THEN** available teardown runs without relying on the test credential
- **AND** incomplete restoration retains a token-free recovery journal
- **AND** a separate admin recovery action verifies restoration before clearing it.

#### Scenario: Unsafe preconditions
- **WHEN** identities match, caller is not the bootstrap root, the caller lacks
  an accepted required charter, or another campaign/recovery is active
- **THEN** the campaign performs no role mutation.
