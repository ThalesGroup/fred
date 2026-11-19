---
schema: 1
title: "Regroup the admin self-test into families and add checks across the platform"
impact: none
configuration: none
configuration_reason: "Frontend-only change to the admin self-test page; no configuration key, default, chart value or backend API changes."
no_action_reason: "No deployment or configuration action is required. The optional role campaign changes a dedicated test account only after explicit confirmation and keeps a credential-free recovery record in its browser."
---
## Applicability

Existing Fred deployments upgrading to this release. Only platform
administrators see the self-test page.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

The self-test page now groups its checks into families with a **Run all**
action and one combined report. A run creates temporary folders, documents,
prompts, conversations and agents in the admin's personal space, and the teams
family creates one disposable team. Every one of them carries the run's token
in its name and is deleted at the end of the run.
Authorization appears last and explains which checks use the current admin
session. Its two-account and session-expiry checks are separate actions.

## Validation

As a platform admin, open Administration, then Self-test, and select Run all.
Each family reports its steps, and the copied full report lists every family
that ran.

The second-account form exposes only **Test roles and isolation**. On Keycloak,
select the dedicated account and enter its password if direct grant is enabled.
On Entra ID or another OIDC provider, sign in as that account in a private
browser window and paste its API access token, not its ID token. There are no
manual expected-role inputs or teams to choose: the campaign assigns test roles
and creates its disposable teams automatically.

### Focused isolation and role campaign

Use the separate **Test roles and isolation** action with a dedicated second
account. The signed-in administrator must be the bootstrap root and must have
accepted the configured team-admin charter. The confirmation explains the
temporary privilege changes, including platform-admin access for the test
account. Keycloak uses the selected account/password; Entra ID uses the
independent API access token above. Authentication provider groups are unchanged:
the campaign manages application roles through existing OpenFGA-backed APIs.

The normal path performs 149 actual checks including transport and recovery,
with at most one extra interruption step (150 total). It does not run the exhaustive
combination matrix behind summarized rows. Coverage is deliberately focused:

- No platform role and each of the five roles separately, with one representative
  privileged route per role and admin-route refusals for delegated roles.
- Public/private team profiles: nonmember, member, editor, analyst, the
  charter-resolved admin (active or pending), and its editor/analyst union.
- Exact team role/permission projections, own-team and foreign-team prompt
  reads, temporary prompt writes and post-revocation read/write refusals.
- Member/session/agent team routes for member and nonmember profiles.
- Additional platform role routes for an unprivileged account, platform admin
  and the corresponding delegated roles.
- Reciprocal personal discovery and eight catalog reads while the
  second account holds platform-admin access. An exact prompt fixture in the
  current admin's space also verifies the other account's read/write refusals.
  Only this personal space receives temporary writes, so recovery never needs
  the second account's credential. The reverse exact fixture/write probe is not
  performed; reciprocal catalog isolation still is. Existing collaborative
  teams are never mutated.

Keep the page open and the second credential valid. Do not administer these
roles or run a campaign in another browser at the same time. Original direct
platform roles and run-team/prompt intentions are saved before mutation in
localStorage under `selftest-role-campaign-v1`. No credential is persisted.
The browser lock prevents overlapping campaign/recovery tabs on the same
origin; it is not a server-wide lock. A browser with Web Locks support is required.

After an interruption, use **Restore original roles and clean up** in the same
browser, origin and profile, signed in as the original bootstrap root. Recovery
does not need the second account's credential. It verifies exact prompt identity
before deletion, removes only verified run teams and clears the journal only
after original direct roles and cleanup are confirmed. If recovery fails, keep
the journal and use its original roles, team names and prompt identities for
manual recovery. Closing the browser cannot run teardown automatically.

## Rollback

Recover any interrupted role campaign before rolling back the frontend, then
use the normal rollback procedure. This change introduces no data migration.

## Limitations

- The teams family is skipped until the admin accepts the team-admin charter;
  the self-test never accepts it on the admin's behalf.
- A run interrupted by closing the tab leaves its run-scoped fixtures behind,
  named with the run token, to delete by hand. The separate role campaign has
  the recovery action described above.
- The security family may fail on deployments that serve uploaded SVG
  previews inline without a sandbox policy. That result reports existing
  behaviour, not a regression introduced by this release.
- The second-account probe is separate from Run all. Its pasted access token
  must remain valid for the duration of the probe; obtain a new one if it
  expires.
- If a prompt's identity cannot be verified after a failed create or its
  deletion fails, the report names the temporary prompt for manual cleanup.
- Private-team nonmembership is checked through the independent admin member
  roster and the target's denied metadata/content reads.
- Platform observation access skips when the KPI backend returns 503 for
  both accounts; it does not claim the role gate was proven in that case.
