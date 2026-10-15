## 1. Backend model and migration

- [ ] 1.1 Add `kind` (`free` | `team`, server default `free`) to `PlatformAccessLinkRow` and one linear Alembic revision on the current swift head; verify `alembic heads` shows one head and a real `alembic upgrade head` / `downgrade -1` round-trip.
- [ ] 1.2 Make `PlatformAccessStore.link()` kind-aware (`free` requires the Free flag, `team` does not); verify with store tests for both kinds, revoked, expired, personal team.

## 2. Backend service and routes

- [ ] 2.1 Thread `kind` through create/list/joiners/reveal/revoke/cleanup so each family only sees its own kind; verify a link id of the other kind answers 404 and cleanup leaves the other kind untouched.
- [ ] 2.2 Add the six `/teams/{team_id}/join-links` routes gated on `can_administer_members`; verify team admin allowed, member/non-member/platform-admin-only refused, personal team refused, reveal requires an own human credential.
- [ ] 2.3 Enrollment, preview and opening on a `team` link require `PlatformAccess.admitted` before any write; verify: admitted caller joins as `team_member` only; non-admitted caller gets `403 team_link_requires_platform_access` with no team name, no membership, no admission, no counter change; joining an authorized or Free team through a `team` link never admits; already-member is a no-op without event; filtering off admits every authenticated caller.
- [ ] 2.4 Audit: `kind` on existing link events, `team.join_link.joined` on a new join; verify events in tests and that no token is logged.

## 3. Frontend

- [ ] 3.1 Regenerate the control-plane client (`make update-control-plane-api`).
- [ ] 3.2 Extract the shared link manager from `PlatformAccessLinkManager`; verify the existing admin tests pass unchanged.
- [ ] 3.3 Add the "Invite link" action next to "Add members" in `TeamSettingsMembers`, team admins only; tests for visibility and opening the manager.
- [ ] 3.4 `FreeEnrollmentPage`: on `403 team_link_requires_platform_access`, replace the location with the existing refusal screen; test.
- [ ] 3.5 Update the stale comment in `TeamSettingsParameters`; fr+en strings.

## 4. Docs and close-out

- [ ] 4.1 `CONTROL-PLANE-PRODUCT-CONTRACT.md` dated entry; `COMPONENT-UX.md`; Help Center `features/teams-and-permissions.md` fr+en.
- [ ] 4.2 Migration note (operations: schema migration) per `MIGRATION-GUIDES.md`.
- [ ] 4.3 `make code-quality`, `make test`, ruff import order, basedpyright; record evidence; `openspec validate team-join-link --strict`.
