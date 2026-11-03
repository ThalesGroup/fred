## Why

The admin self-test page proves a handful of journeys: retrieval scoped to two
folders, prompt delivery, web research, JWT handling, a single-account
authorization probe and the credential-expiry check. Most of the platform is
never exercised on a live deployment: health of each service, model and runtime
readiness, document formats, revocation, agent copy, team lifecycle, wiki,
conversations, observability and response safety. A broken deployment is found
by a user instead of by the admin.

The page also grew one section at a time. Its first section mixes retrieval,
agent tuning and prompt delivery in one scenario, and every new check would
add another hand-wired section.

## What Changes

- Regroup the page into **families**, one scenario each, rendered from one
  registry with the same report panel: platform, identity, knowledge, agents,
  prompts, conversations, teams, web research, security, observability and
  authorization. A notice explains the final family's purpose and its separate
  two-account and session-expiry checks.
- Split the existing functional scenario into the knowledge, agents and prompts
  families, and delete it.
- Add checks to every family. Run all acts as the signed-in admin, on the real
  deployment, with run-scoped fixtures removed at the end. The separate
  authorization probe can use a second account's temporary access token.
- Use one automatic two-account role/isolation campaign, with no manual roles
  or team selections, at most 150 actual checks including restoration.
- Add **Run all**, which runs every family in order except the long
  credential-expiry check, and one combined report to copy.
- The teams family works in a disposable team the admin creates for the run and
  deletes at the end. It is skipped when the admin has not accepted the
  team-admin charter; the run never accepts it on the admin's behalf.

## Capabilities

### Modified Capabilities

- `admin-self-test`: page organization, run-all, and the checks of each family.

## Impact

Frontend only: `apps/frontend/src/rework/features/pipeline/`, the browser auth
service, locales and the self-test page. No backend, API or configuration change. Shared platform settings
(platform prompt, model bindings, announcements, theme) are only read, never
written. The full multi-account authorization matrix stays in `validation/`;
the page checks reciprocal personal-space isolation for two accounts when the
admin supplies a second credential.

## Automatic two-account role campaign

Add a separate, explicitly confirmed campaign that temporarily changes the
test account's application platform roles, exercises each role independently,
and restores the original direct grants. The signed-in bootstrap root keeps
its own roles. Six focused team-role profiles run in disposable public/private
teams, with cross-team/personal isolation and revocation checks. The current
charter determines whether the nominated admin is active or pending. A
token-free local recovery journal survives reloads; a separate recovery action
reconciles grants and removes verified run teams. This campaign is never
included in Run all.

The second-account UI now exposes only this campaign: no expected-role or team
selection and no observation-only run. Its real-check budget is raised to 150
to include missing discovery, personal catalog and exact prompt isolation,
team content and additional platform-route probes.
