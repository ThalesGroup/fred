## Why

A team admin cannot send a link to join their team. Members are added one by one through the candidate search (`GET /teams/{team_id}/candidate-members`), and the team settings say so ("there is no invitation flow either"). Platform administrators already have invitation links (`/join/:token`), but those are Free-team enrollment links: they admit a person to the platform, so they must stay a platform-administrator power.

The owner's decision (2026-10-15, GitHub issue #3116): a team admin can create links to join their own team, usable only by people who already have platform access. A team-admin link never admits anyone to the platform.

## What Changes

- The existing invitation link model gains a `kind`: `free` (today's platform-administrator Free-team enrollment link, unchanged) or `team` (new).
- A team admin (`can_administer_members`) can create, list, copy, revoke and clean up `team` links for their own non-personal team, and see who joined through each link, from the team settings Members tab. Same lifecycle as Free links: optional note, optional expiry, individual irreversible revocation, opening count, joiners list, bulk cleanup of revoked/expired links.
- A `team` link does not depend on the team's Free flag, joining mode or visibility.
- Clicking a `team` link reuses `/join/:token` and the `/platform-access/free/{token}` preview/opening/enrollment endpoints. Platform access is checked first: on a `team` link, preview, opening, terms acceptance and enrollment answer the existing `403 platform_access_denied` to a caller who is not admitted, and the page sends them to the existing refusal screen (`/platform-access-denied`). They never see the invitation or the team name, no opening is counted, and no membership, admission or account is created.
- Joining through a `team` link grants `team_member` only, to the caller only. Already a member: success, no change, no join event.
- Platform administrators' Free-link manager lists `free` links only; the team settings manager lists `team` links only. Links have no use cap, optional expiry, and survive their creator's demotion or departure.

## Capabilities

### New Capabilities

- `team-join-links`: team-admin invitation links that add an already-admitted platform user to one team as a member.

### Modified Capabilities

None. The Free-link requirements in `platform-access-control` keep their meaning; the delta spec states that `team` links stay out of the Free-link history and never admit.

## Impact

- Backend: `platform_access_links.kind` column (one linear Alembic migration on the swift head, default `free` for existing rows); `PlatformAccessStore.link()` and the link service functions become kind-aware; six team-scoped routes under `/teams/{team_id}/join-links` gated on `can_administer_members`; enrollment admission check for `team` links.
- Frontend: regenerated `controlPlaneOpenApi.ts`; the link manager extracted from `PlatformAccessLinkManager` so both managers share one component; an "Invite link" action next to "Add members" in `TeamSettingsMembers`; `FreeEnrollmentPage` redirects a `403 platform_access_denied` to the existing refusal screen (no new state); the stale comment in `TeamSettingsParameters` updated; fr+en strings.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` dated entry (new routes, `kind`, error code, audit events); Help Center `features/teams-and-permissions.md` fr+en; `COMPONENT-UX.md`; migration note (impact: operations, schema migration, no configuration) -> minor version.
- No change to ReBAC schema, `joining_mode`, `POST /teams/{team_id}/join` or platform-administrator link routes.
