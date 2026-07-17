// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type { TeamPermission } from "../../../slices/controlPlane/controlPlaneOpenApi";

/**
 * One boolean per `TeamPermission` the backend can grant on a team
 * (`TeamWithPermissions.permissions`, OpenFGA-derived — see
 * `teams/service.py::_get_team_permissions_for_user`).
 *
 * This is the team-scoped counterpart to `UserCapabilities`
 * (`useUserCapabilities.ts`) for the org-scoped tier. See
 * `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md` for the full pattern.
 */
export type TeamCapabilities = {
  canRead: boolean;
  canUpdateInfo: boolean;
  canUpdateResources: boolean;
  canUpdateAgents: boolean;
  canReadMembers: boolean;
  canAdministerMembers: boolean;
  canAdministerEditors: boolean;
  canAdministerAnalysts: boolean;
  canAdministerAdmins: boolean;
  canReadConversations: boolean;
  canUseTeamAgents: boolean;
  canRunEvaluations: boolean;
  canManageEvaluationCorpus: boolean;
  canReadConversationsForEvaluation: boolean;
};

/**
 * `Record<TeamPermission, ...>` deliberately requires every member of the
 * generated `TeamPermission` union as a key. If the backend adds, renames, or
 * removes a team capability, `controlPlaneOpenApi.ts` regenerates and this
 * map fails to compile until it's updated — a missing capability becomes a
 * build error, not a gap only a manual audit finds.
 */
const PERMISSION_TO_FLAG: Record<TeamPermission, keyof TeamCapabilities> = {
  can_read: "canRead",
  can_update_info: "canUpdateInfo",
  can_update_resources: "canUpdateResources",
  can_update_agents: "canUpdateAgents",
  can_read_members: "canReadMembers",
  can_administer_members: "canAdministerMembers",
  can_administer_editors: "canAdministerEditors",
  can_administer_analysts: "canAdministerAnalysts",
  can_administer_admins: "canAdministerAdmins",
  can_read_conversations: "canReadConversations",
  can_use_team_agents: "canUseTeamAgents",
  can_run_evaluations: "canRunEvaluations",
  can_manage_evaluation_corpus: "canManageEvaluationCorpus",
  can_read_conversations_for_evaluation: "canReadConversationsForEvaluation",
};

const ALL_DENIED: TeamCapabilities = Object.fromEntries(
  Object.values(PERMISSION_TO_FLAG).map((flag) => [flag, false]),
) as TeamCapabilities;

/**
 * Turn the raw `TeamPermission[]` the backend returns for one (user, team)
 * pair into named booleans. Pure — no React, no fetching, nothing to mock in
 * a test.
 */
export function mapTeamPermissions(permissions: TeamPermission[] | null | undefined): TeamCapabilities {
  if (!permissions || permissions.length === 0) {
    return ALL_DENIED;
  }
  const flags = { ...ALL_DENIED };
  for (const permission of permissions) {
    const flag = PERMISSION_TO_FLAG[permission];
    if (flag) {
      flags[flag] = true;
    }
  }
  return flags;
}
