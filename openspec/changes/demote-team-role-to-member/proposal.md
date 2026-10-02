## Why

Tracking issue: #2925.

Turning off a member's only elevated team role currently fails with HTTP 409 because that role is their only stored membership relation. The members table still shows the computed Member badge, so an administrator reasonably expects the person to remain a simple member. Enabling the team administrator charter makes the same case visible for `pending_team_admin`.

## What Changes

- Revoking the only stored elevated role (`team_admin`, `pending_team_admin`, `team_editor`, or `team_analyst`) leaves a direct `team_member` relation so the person remains on the team.
- Keep full member removal as the explicit delete-member action. Revoking `team_member` when it is the only stored relation still fails.
- Keep the existing permission checks and the rule requiring at least one active `team_admin` on a team.
- Cover the members table toggle and backend role-revocation contract with focused tests.

## Capabilities

### New Capabilities

- `team-member-roles`: Team role grants, revocations, retained membership, and the member-management UI.

### Modified Capabilities

None.

## Impact

- `DELETE /control-plane/v1/teams/{team_id}/members/{user_id}/roles/{relation}` changes behavior for a member whose only stored relation is an elevated role: the request succeeds and retains them as `team_member` when authorization and the last-admin guard pass.
- Control-plane team role service, focused tests, and the frontend members table. No request or response schema change is expected.
- The team-role sections of `REBAC.md` and `CONTROL-PLANE-PRODUCT-CONTRACT.md` need to reflect the new revocation behavior.
