## Context

Platform administrators manage Free-team invitation links (`platform_access/service.py`, `PlatformAccessLinkRow`, landing page `FreeEnrollmentPage` at `/join/:token`): a hashed 256-bit token, recoverable for own-human copy, valid only while the team has the Free flag. Joining a Free team is itself an admission source, so a Free link turns any signed-in account into a platform user.

Team membership writes are gated on `can_administer_members` (`team_admin` only, see `REBAC.md`).

"Platform user" means a person admitted by platform access (`PlatformAccess.admitted`): any authenticated person when filtering is off, an admitted person when it is on. Fred never creates accounts.

## Goals / Non-Goals

**Goals:** one URL per team that a team admin can pause, resume and replace; an admitted person who opens it becomes `team_member`; anyone else is refused without learning anything.

**Non-Goals:** several links, expiry, use caps, opening counters or joiner lists for team links, e-mail delivery, roles above member, showing team links to platform administrators, changing Free links, merging the admin route family (follow-up cleanup issue).

## Decisions

### 1. Reuse the link table: `kind` and `paused`

`platform_access_links.kind` (`free` | `team`, default `free`) and `paused` (boolean, default false; used by team links only). Token generation, hashing, recoverable plaintext, the join endpoints, access-log redaction and the `/join/:token` page are shared.

- A team has at most one `team` row. First enabling inserts it; pausing and resuming flip `paused` on the same row, so the URL never changes; regenerating deletes the row and inserts a new enabled one, so the old token resolves to nothing.
- `PlatformAccessStore.link()` accepts a team link only when it is not paused, and a Free link only while the Free flag is on. Paused and replaced links therefore answer the existing `404 free_enrollment_link_invalid`, which the join page already shows as "This invitation link is no longer valid". No team name, nothing counted.
- Free-link administration (list, joiners, reveal, revoke, cleanup) filters `kind = free`; a team link id answers 404 there.
- Team-link joins write no joiner row: there is no screen for it.

Alternatives rejected: a separate team-link table and landing page (duplicates token machinery, against the prime directive); pausing through `revoked_at` (revocation is irreversible for Free links, and overloading it would blur both meanings); keeping the multi-link history UI (the owner found it too heavy).

### 2. Platform access before any effect

On a valid team link, preview, opening, terms acceptance and enrollment check `PlatformAccess.admitted(user)` before the team name, opening count, terms acceptance or membership. Only the caller's ordinary user-row observation, done on every authenticated request, precedes it. A non-admitted caller gets `403 team_link_requires_platform_access`. It is deliberately not `platform_access_denied`: the shared API layer resets the whole client store on that code, which would leave the join page unable to read the answer. The page replaces the location with `/platform-access-denied`. The caller is not yet a member, so joining an authorized or Free team through a team link can never admit.

### 3. Routes and permissions

`GET /teams/{team_id}/join-link` → `{enabled, token}`; `PUT` `{enabled}`; `POST .../regenerate`. All require `can_administer_members` (higher consistency) and the caller's own human credential (the response carries the reusable URL, like the administrators' reveal), answer `Cache-Control: no-store`, and refuse personal teams. Audit: `team.join_link.enabled|paused|regenerated` and, on a new join, `team.join_link.joined`; never the token. Joining mode and visibility are not consulted. Links survive their creator's demotion or departure.

### 4. Frontend

`TeamInviteLinkDialog` (shared organism next to `AddTeamMembersDialog`) reads the state and calls the two mutations. While the switch is off, everything below it is disabled, still showing the URL if one exists. Copy writes to the clipboard; on refusal the URL is focused and selected with an alert. The Members tab button is shown to team admins only when `platform_access_enabled` is true. The platform-admin `PlatformAccessLinkManager` is unchanged.

### 5. Free admission comes from Free-link joins only

Owner principle: a team admin must never be able to grant platform access. Before this change the Free source was any current membership of a Free team, so a rule-admitted person who joined a Free team through a team link (or was added by hand) kept platform access after the rule was tightened. Now `PlatformAccess.team_sources` returns, per eligible team the person is a member of, whether it is authorized (every member admitted, unchanged) and whether it is Free with a recorded joiner row of a `free` link of that team. The same evidence drives request admission on every backend, the activation preview (one joiner query for all users) and the whitelist sources. Enrollment through a Free link records a joiner whenever none exists for that person and link, including for an existing member. Team links never record one.

Consequences: existing Free-team members without a joiner row (added by hand, by team link, or joined before joiners were recorded) lose that source on upgrade; deleting revoked or expired Free-link history (cleanup) deletes its joiners and so withdraws the source they provided; a Free joiner who leaves and is later re-added still has the recorded join. Readers now require the link and joiner tables at startup.

Alternative considered: a dedicated "admitted via Free" flag on membership. Rejected: the joiner table already records exactly that event.

## Risks / Trade-offs

- A team admin can bring any admitted user into a private team -> same power as the manual add; the link can be paused or replaced at any time.
- A leaked link lets any admitted person join -> pause or regenerate.
- "Generate a new link" has no confirmation -> one click kills the shared URL; acceptable because a new one is shown immediately.

## Migration Plan

Revision `c3a7e5d9f1b2` on swift head `24c2f88374fe` adds both columns with server defaults. Downgrade deletes team rows, then drops the columns. Migration note: minor.

## Owner decisions (2026-10-15)

1. Platform access first; a non-admitted person goes straight to the existing refusal screen, never sees the team name, nothing counted.
2. No use cap, no expiry.
3. Links survive their creator's demotion or departure.
4. Platform administrators do not see team links.
5. UI: Members tab, "Invite link" next to "Add members"; after testing, one link per team behind a switch, Copy, Generate a new link, no lists or counters.
6. Route-family merge of the admin links: later, separate cleanup issue.
7. A paused or replaced link shows the existing invalid-link state of the join page.
8. After a successful join (or an already-member retry) through any invitation link, the person lands on the team's page (`team/{team_id}/agents`): the enroll answer carries `team_id` when the caller is admitted.
9. A team admin must never grant platform access: Free admits only Free-link joiners while they are members and Free is on; authorized teams unchanged.

No open questions remain.
