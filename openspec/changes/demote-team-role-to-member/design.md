## Context

The OpenFGA `team_member` relation is both a directly stored baseline and a computed union of elevated roles. `GET /teams/{team_id}/members` shows the baseline badge even when no direct baseline tuple exists. `revoke_team_member_role` reads direct tuples and currently rejects removal of the sole one. See proposal.md for the resulting UI problem.

## Goals / Non-Goals

**Goals:**

- Make the existing role toggle retain team membership after the final elevated role is removed.
- Keep the existing authorization and last-active-admin checks as the source of truth in the control-plane.

**Non-Goals:**

- Change member deletion, role grants, the OpenFGA model, or charter acceptance and reconciliation.
- Solve concurrent last-admin revocations, tracked separately by issue #1985.

## Decisions

### Convert the sole elevated role in the existing revoke service

After reading the target's direct roles, the service identifies a sole elevated role. It runs the existing last-admin guard for `team_admin` and checks both the permission for the requested revoke and `can_administer_members` before any write. These permissions currently both derive from `team_admin`, so cancelling a pending nomination requires an active administrator. A pending nomination does not count toward the existing last-active-admin guard. It then grants a direct `team_member` relation and revokes the elevated relation. If another stored role exists, it keeps the current single-role revoke path. A sole `team_member` still raises `TeamMemberLastRoleError`.

This keeps the frontend's existing one-click toggle and the API's existing request shape. A frontend-only grant-then-revoke sequence was rejected: the member-list projection hides a direct baseline tuple whenever an elevated role is present, so the client cannot safely decide whether a grant would duplicate a tuple. A new endpoint would duplicate the existing revoke surface for this one outcome.

### Serialize demotion with full member removal

Both role revocation and explicit member removal hold the same Postgres advisory lock for the target team and user from the first direct-role read through their relation writes. They force a higher-consistency OpenFGA role read after acquiring the lock, so a waiting revoke cannot see roles that a completed removal has deleted. Team metadata is loaded before acquiring the lock to avoid taking a second database connection inside the critical section. This prevents a stale demotion from granting `team_member` after a concurrent full removal. It works across control-plane replicas. The lock is scoped to one team member; concurrent revocations of two different administrators still need the separate last-admin concurrency fix.

### Add the baseline before removing the elevated role

The two writes are ordered so an interrupted request cannot silently remove the person's last membership relation. If the second write fails, the person keeps the elevated role and gains an explicit baseline; retrying the same revoke removes only the elevated role. This uses the existing audited relation-write path. No schema or client generation is needed because the route signature and response stay the same.

## Risks / Trade-offs

- [A failure after the baseline grant leaves an extra direct relation while the elevated role is still held] -> The person remains a member with the original authority; retrying the revoke completes the demotion. Focused tests cover write order and retry.
- [Last-admin checks can race between concurrent requests] -> Preserve the existing guard and leave cross-request synchronization to issue #1985.

## Migration Plan

Deploy the control-plane change before relying on this toggle for sole-role demotions. No data migration is required. Rolling back restores the old 409 behavior; already-demoted members keep their direct `team_member` relation.
