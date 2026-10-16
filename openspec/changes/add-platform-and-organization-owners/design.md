## Context

Decided on 2026-10-15 with Maxime. Platform: one technical role, `owner`, held by root
and anyone root or another owner names. Organization: a technical `owner` (names the
organization's admins; later quotas and FinOps) beside the business roles admin,
editor, analyst and member. Teams and projects have business roles only. `admin` is
always business: it creates child spaces and names roles in its space and below.

## Decisions

- **Platform model.** `platform:root` relation `admin` is renamed `owner`;
  `team_manager` and `can_create_team` are removed. `observer`, `feature_manager` and
  `prompt_editor` union `owner` as they unioned `admin`. Every other platform
  permission maps from admin to owner. The typed role and wire name become
  `platform_owner`, with `owner` accepted as an import alias.
- **Platform owner administration.** Any platform owner grants and revokes platform
  owners and the other platform roles. Revoking the last platform owner is refused
  under the platform lock. Bootstrap still promotes one person once; that grant is
  an ordinary owner grant afterwards.
- **Organization owner.** `space` gains `owner: [user]` and `can_own: owner`. Manager
  writes `owner` only on organizations. It grants no content, descends nowhere and
  requires no parent. `Role::Owner` is listed with the caller's roles.
- **Who changes what.** Owner on an organization: platform owner. Admin on an
  organization: organization owner or admin. Every other space role: `can_manage`
  on the space, as today. Revoking the last owner of an organization is refused,
  as for the last admin of a non-personal space.
- **Creation.** `create-org <name> <user>` grants owner, admin and member. Import
  requires a declared owner and admin for a new organization and refuses owner on
  teams and projects; declaring an owner requires a platform owner caller, which
  import already requires.
- **No delegated team creation.** Team creation needs `can_manage` on the
  organization and no longer takes the platform lock.

## Costs

Granting or revoking an organization admin adds at most one Check (`can_own`) when
the caller does not manage the organization. Revoking an owner reads the owners of
that organization (`P_o` pages). Team creation loses one guard Read and the platform
Check. Platform owner grants keep their cost; their revocation reads all platform
grants, as before.

## Risks / Trade-offs

- Any platform owner can remove root. The last-owner rule prevents an ownerless
  platform, not a takeover by another owner.
- Existing manager data and Python role names differ: a local reset is required;
  Python services keep their own catalog until they move to manager.
