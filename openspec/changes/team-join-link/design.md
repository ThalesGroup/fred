## Context

Platform administrators already manage invitation links (`platform_access/service.py`, `PlatformAccessLinkRow` / `PlatformAccessLinkJoinerRow`, `PlatformAccessLinkManager.tsx`, landing page `FreeEnrollmentPage` at `/join/:token`). A link is a hashed 256-bit token with note, expiry, revocation, opening count, recoverable plaintext for own-human copy, a joiners table and bulk cleanup. It is valid only while its team has the Free flag, and joining a Free team is itself an admission source, so a Free link turns any signed-in Keycloak account into a platform user.

Team membership writes are gated on `can_administer_members` (`team_admin` only, no platform escalation, see `REBAC.md`), except `POST /teams/{team_id}/join`, which lets anyone join an `open` team as `team_member`.

"Platform user" here means a person admitted by platform access (`PlatformAccess.admitted`): any authenticated person when filtering is off, an admitted person when it is on. Fred never creates Keycloak accounts; "creating a platform user" means admitting one.

## Goals / Non-Goals

**Goals:** a team admin shares one URL; an admitted person who opens it becomes `team_member`; a non-admitted person gets a clear refusal and nothing changes.

**Non-Goals:** e-mail delivery, granting roles above member, usage caps, access requests, changing Free links or the platform-administrator screens beyond filtering by kind, merging the two route families (see Decision 2).

## Decisions

### 1. Reuse the link table with a `kind` column

`platform_access_links.kind` (`free` | `team`, not null, server default `free`). Everything else (token hashing, reveal, revoke, expiry, opening count, joiners, cleanup, log redaction, the `/join/:token` page) is shared.

- Validity: `free` requires the team's Free flag (unchanged); `team` does not.
- Enrollment: for `team`, call `PlatformAccess.admitted(user)` before writing the membership. The caller is not yet a member, so the check cannot be satisfied by the team being joined, even when that team is authorized or Free. Refusal: `403 team_link_requires_platform_access`.
- Preview and opening on a `team` link by a non-admitted caller return the same 403 without the team name, so the link reveals nothing to someone who cannot use it.
- Kind is fixed at creation and never changes.

Alternative rejected: a separate `team_join_links` table and landing page. It would duplicate token handling, reveal, revocation, expiry, counters, joiners, cleanup, access-log redaction and the landing page, against the prime directive. Cost of reuse: the code stays in `platform_access/`; its service functions already take `team_id`, so team routes call them with a different authorization dependency and an explicit kind filter.

### 2. A team-scoped route family, sharing the service

`/teams/{team_id}/join-links` (POST create, GET list, GET `{link_id}/joiners`, POST `{link_id}/reveal`, DELETE `{link_id}`, DELETE `inactive`), gated on `can_administer_members` through `_validate_team_and_check_permission`, always `kind=team`. The existing `/admin/platform/access/teams/{team_id}/enrollment-links*` routes stay `CAN_MANAGE_PLATFORM` and become `kind=free`. A link id of the other kind answers 404.

Alternative considered: one route family for both kinds, authorized per kind. Fewer routes, but it breaks the platform-administrator API and generated client in the same change. Left as an open question for a later reduction.

### 3. Permissions and lifecycle

- Create/list/copy/revoke/cleanup/joiners: `can_administer_members` on the team (team admins; a platform admin only if also team admin). Personal teams refused (`personal_team_not_eligible`, existing).
- Copy (reveal) keeps the own-human-credential rule of Free links.
- Links survive the creator's demotion or departure; any team admin of the team manages them. Team deletion cascades (existing FK).
- Joining mode and visibility are not consulted: the link is the invitation, for `invite_only` and `private` teams too.
- Granted relation: `team_member` only, caller only, via `_add_team_member_relation`; CGU and suspension checks unchanged.
- No new rate limit: tokens are 256-bit and each use only adds the caller.

### 4. Audit

Existing `platform.access.link.created|revealed|revoked` and `platform.access.links.deleted` gain a `kind` field. A successful new join through a `team` link emits `team.join_link.joined` (actor, team, link). No token in any event.

### 5. Frontend

Extract the list/create/copy/revoke/cleanup/joiners UI of `PlatformAccessLinkManager` into one shared manager fed with the generated hooks of either route family; the Free-specific parts (Link access toggle, suspended notice) stay on the admin side. `TeamSettingsMembers` gets an "Invite link" action for team admins. `FreeEnrollmentPage` maps `403 team_link_requires_platform_access` to a card telling the person to ask a platform administrator, with `contactSupportLink` when configured, and no join button.

## Risks / Trade-offs

- A team admin can bring any admitted user into a private team without that user being searched first -> same power as today's manual add; joiners are listed and links revocable.
- Shared code means a Free-link change can affect team links -> kind-specific tests on both route families.
- A leaked team link lets any admitted person join -> expiry, revocation and the joiners list, as for Free links.

## Migration Plan

One Alembic revision on the swift head (`24c2f88374fe` at time of writing; re-parent before merge if swift moves): add `kind` with server default `free`. Rollback drops the column after deleting `team` rows. Migration note: operations impact (schema migration), minor version.

## Open Questions

Each has a recommendation; the draft above assumes it.

1. Hide the team name from a non-admitted caller? Recommended: yes, 403 with no preview.
2. Usage cap or mandatory expiry? Recommended: neither, same optional expiry as Free links; revocation and joiners cover misuse.
3. Do links survive their creator's demotion or departure? Recommended: yes, they belong to the team.
4. Should platform administrators see every team's `team` links from the admin page? Recommended: no in this slice.
5. Where in the UI? Recommended: Members tab, an "Invite link" action next to "Add members".
6. Merge the two route families into one, authorized per kind? Recommended: separate follow-up reduction issue, not this change.
