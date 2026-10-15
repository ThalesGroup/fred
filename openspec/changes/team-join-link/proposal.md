## Why

A team admin cannot send a link to join their team. Members are added one by one through the candidate search (`GET /teams/{team_id}/candidate-members`). Platform administrators already have invitation links (`/join/:token`), but those are Free-team enrollment links: they admit a person to the platform, so they must stay a platform-administrator power.

The owner's decision (2026-10-15, GitHub issue #3116): a team admin can share one link to join their own team, usable only by people who already have platform access. A team link never admits anyone to the platform. After testing a first multi-link version, the owner asked for the simplest form: one link per team behind a switch.

## What Changes

- The existing invitation link table gains `kind` (`free`, today's Free-team links, unchanged; or `team`) and `paused`.
- A team admin (`can_administer_members`) opens **Invite link** in the Members tab: a switch "Enable invitation by link", the full URL with **Copy**, and **Generate a new link**. One link per team. First enabling creates it; the switch pauses and resumes the same URL; regenerating replaces it for good and leaves the invitation on. No expiry, history, counters, joiners list or cleanup.
- Clicking a team link reuses `/join/:token` and the `/platform-access/free/{token}` endpoints. A paused or replaced link answers the existing invalid-link `404`, so the page shows "This invitation link is no longer valid". On a valid team link, a caller without platform access gets `403 team_link_requires_platform_access` before any membership, opening or terms effect, and the page sends them to the existing refusal screen, without the team name.
- Joining grants `team_member` only, to the caller only. Already a member: no change.
- Platform administrators' Free-link screens and routes cover Free links only.

## Capabilities

### New Capabilities

- `team-join-links`: a team's single pausable invite link that adds an already-admitted platform user as a member.

### Modified Capabilities

None. The Free-link requirements in `platform-access-control` keep their meaning; the delta spec states that team links stay out of Free-link administration and never admit.

## Impact

- Backend: two columns on `platform_access_links` (linear revision `c3a7e5d9f1b2` on swift head `24c2f88374fe`); `PlatformAccessStore.link()` kind-aware; three routes `GET|PUT /teams/{team_id}/join-link`, `POST /teams/{team_id}/join-link/regenerate`; admission check on the join endpoints for team links.
- Frontend: regenerated `controlPlaneOpenApi.ts`; new `TeamInviteLinkDialog` under `TeamSettingsMembers`; the button is hidden without platform access; `FreeEnrollmentPage` redirects `team_link_requires_platform_access` to the refusal screen; fr+en strings. The platform-admin link manager is unchanged.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` dated entry, `authz-endpoint-matrix.yaml`, Help Center fr+en, `COMPONENT-UX.md`, migration note (minor: schema migration).
