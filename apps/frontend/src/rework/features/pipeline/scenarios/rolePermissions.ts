// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
import type {
  PlatformRoleRelation,
  UserTeamRelation,
  TeamPermission,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

export const PLATFORM_ROLES: PlatformRoleRelation[] = [
  "platform_admin",
  "platform_observer",
  "team_manager",
  "feature_manager",
  "prompt_editor",
];
export const TEAM_ROLES: UserTeamRelation[] = [
  "team_admin",
  "pending_team_admin",
  "team_editor",
  "team_analyst",
  "team_member",
];

// Keep this projection aligned with schema.fga. It supplies an independent
// expectation instead of treating the backend's permissions as their own proof.
const TEAM_PERMISSION_ROLES: Record<TeamPermission, UserTeamRelation[]> = {
  can_read: TEAM_ROLES,
  can_update_info: ["team_admin"],
  can_update_resources: ["team_editor"],
  can_update_agents: ["team_editor"],
  can_read_members: TEAM_ROLES,
  can_administer_members: ["team_admin"],
  can_administer_editors: ["team_admin"],
  can_administer_analysts: ["team_admin"],
  can_administer_admins: ["team_admin"],
  can_publish_marketplace_agents: ["team_editor"],
  can_unpublish_marketplace_agents: ["team_editor", "team_admin"],
  can_read_conversations: TEAM_ROLES,
  can_use_team_agents: TEAM_ROLES,
  can_use_team_applications: TEAM_ROLES,
  can_use_team_knowledge_bases: TEAM_ROLES,
  can_access_files: TEAM_ROLES,
  can_run_evaluations: ["team_analyst", "team_admin"],
  can_manage_evaluation_corpus: ["team_analyst", "team_admin"],
  can_read_conversations_for_evaluation: ["team_analyst"],
};

export function expectedTeamPermissions(roles: UserTeamRelation[], visibility: string): TeamPermission[] {
  return (Object.keys(TEAM_PERMISSION_ROLES) as TeamPermission[]).filter(
    (permission) =>
      (permission === "can_read" && visibility === "public") ||
      TEAM_PERMISSION_ROLES[permission].some((role) => roles.includes(role)),
  );
}
