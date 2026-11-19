// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// Business owner first, then editor and analyst, in a stable order regardless of
// the raw relation order the bootstrap returns. `team_member` is the implicit
// baseline and is only shown (as the sole label) when no elevated role is held.
const ROLE_PRIORITY: Record<string, number> = {
  team_owner: 0,
  team_admin: 0,
  pending_team_admin: 0,
  team_editor: 1,
  team_analyst: 2,
};

/** Shared role wording for the Home list and the team header; grants no permissions. */
export function teamRoleLabel(roles: readonly string[], t: (key: string) => string): string {
  const heldRoles = roles
    .map((role) => (role.startsWith("team_") || role === "pending_team_admin" ? role : `team_${role}`))
    .filter((relation) => relation in ROLE_PRIORITY)
    .slice()
    .sort((a, b) => ROLE_PRIORITY[a] - ROLE_PRIORITY[b]);
  return heldRoles.length === 0
    ? t("rework.teamRoles.team_member")
    : heldRoles.map((relation) => t(`rework.teamRoles.${relation}`)).join(" · ");
}

/** Caption under a space header: roles beyond plain membership, which goes without saying. */
export function spaceRolesCaption(roles: readonly string[], t: (key: string) => string): string | undefined {
  // The technical organization admin is not a business role: it never reads as one here.
  const extra = roles.filter((role) => role !== "member" && role !== "organization_admin");
  return extra.length > 0 ? teamRoleLabel(extra, t) : undefined;
}
