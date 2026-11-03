## Context

See [proposal.md](proposal.md). Verified constraints:

- Run all uses the admin's browser identity. The optional second-account probe
  uses Keycloak direct grant in test realms or a pasted API access token from
  a separate OIDC browser session. The token stays in memory for that run.
- A platform admin has no relation on any team. Team checks therefore need a
  team the admin creates and administers. Creation writes `pending_team_admin`
  until the creator accepted the team-admin charter, so the family is skipped
  without an accepted charter.
- The deterministic `fred.github.self_test` agent echoes retrieved chunks, its
  system prompt and the session's context prompt without an LLM. Turn-based
  checks assert on that echo.
- Regular family calls made as the admin go through the generated RTK Query client,
  dispatched with `initiate` as `useTaskPolling` already does. Raw `fetch` is
  used only where the generated client cannot express the check: no token, a
  forged token, or a response header.

## Decisions

- **One scenario and one deps contract per family.** A scenario depends only on
  its narrow deps interface, so each family is unit-tested with fakes. A hook
  binds the real client for that family.
- **Run-scoped fixtures, deleted by id.** Every created object carries the run
  token in its name; teardown deletes only the ids the run created and then
  verifies they are gone.
- **Read-only on shared state.** Checks on the platform prompt, model bindings,
  UI settings and announcements only read them.
- **Missing optional deployment features skip.** A disabled wiki, an absent
  OpenSearch or Prometheus, or an unset proxy header is reported as skipped
  with the reason, not failed.
- **Response safety fails.** An uploaded SVG previewed inline without a
  sandboxing policy fails, because opened as a document it runs on the
  platform origin. HTML is not tested: the default ingestion profile has no
  HTML processor.
- **Formats checked against the real processors.** Each format fixture was fed
  to the default profile's processors locally, and each extracted its marker.
  An Excel table goes to tabular storage, not to text, so the Excel fixture is a
  single text cell.
- **Second-account identity comes from the API.** Both access tokens must
  pass `/frontend/bootstrap`; its `current_user.id` must differ. The probe
  checks each user's personal routes with both tokens and never stores or
  prints the pasted token.

## Non-Goals

- No new backend endpoint or headless runner. Running the families from a
  pipeline is a separate decision.
- No change to the credential-expiry or web-research checks.

## Risks

- A deployment with a large corpus makes the corpus audit slow. The audit step
  is optional and reports anomalies without blocking the rest of the family.

## Automatic campaign

The developer approved automatic role changes and restoration on 21 October.
Preflight resolves both canonical identities, requires the caller to be the
bootstrap root and the target not to be that root, and checks the caller's
charter before mutations. Snapshot direct grants before any write. Application
roles are OpenFGA relations for Keycloak and Entra ID alike, not IdP groups.

Test no platform role and each of the five platform roles, with a representative
allowed route and an admin-route denial for delegated roles. Clear platform
grants for the independent team checks. Test six team profiles for both
visibilities: nonmember, member, editor, analyst, the charter-resolved
administrator role, and its editor/analyst union. Do not enumerate incompatible
charter combinations. Keep an accepted administrator in each team and verify
membership through its independent member roster. Role transitions add desired
relations before removing old ones, accounting for last-role fallback.
Nonmembership and no-platform-role checks exercise revocation. Reciprocal
personal-space metadata, prompt, session and agent reads run with the target
as platform admin. This is bounded representative coverage, not an exhaustive
Cartesian product or every product operation.

Persist original grants and run-team names before mutations, without tokens.
Use an origin-wide browser lock for campaign/recovery exclusion. Teardown runs
in finally and independently attempts every restoration/cleanup item. Verify
restored direct grants and registry absence before clearing the journal. A
closed browser cannot perform teardown: keep a visible recovery action and
precise manual recovery information. Campaign requests use explicit credentials
for both identities, including a refreshable administrator credential, instead
of switching the application's active session. Never modify existing team roles, the
charter, IdP settings or shared product configuration. New team creation with
a lost response is recovered by exact run name and description.

## Single campaign consolidation

The developer replaces the manual expected-role/team probe with the automatic
campaign alone. Credentials are shared with no observation-only action. Add
personal discovery and catalogs, representative missing platform routes, team
member/session/agent reads for nonmembers and members, and exact personal
prompt isolation. Personal mutations are restricted to the current admin's
space so recovery never needs an expired second credential; reciprocal personal
catalog reads remain checked. Persist personal prompt intentions too, accepting
only the recorded admin's personal team at recovery. No arbitrary teams are
selected or mutated. Budget: at most 150 actual report steps, including
transport, restoration and interruption. This supersedes the 99-check limit
and manual-role interface described earlier.
