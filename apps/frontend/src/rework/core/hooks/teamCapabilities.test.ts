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

import { describe, it, expect } from "vitest";
import { canEditTeamContent, mapTeamPermissions, type TeamCapabilities } from "./teamCapabilities";
import type { TeamPermission, UserTeamRelation } from "../../../slices/controlPlane/controlPlaneOpenApi";

// Every `TeamPermission` the generated client currently knows about, paired
// with the flag it must turn on and nothing else. If the backend adds a
// capability, `TeamPermission` gains a member, `teamCapabilities.ts` fails to
// compile until the map is updated, and this list should grow to match —
// the compiler enforces the map, this test enforces the *behaviour*.
const CASES: Array<[TeamPermission, keyof TeamCapabilities]> = [
  ["can_read", "canRead"],
  ["can_update_info", "canUpdateInfo"],
  ["can_update_resources", "canUpdateResources"],
  ["can_update_agents", "canUpdateAgents"],
  ["can_read_members", "canReadMembers"],
  ["can_administer_members", "canAdministerMembers"],
  ["can_administer_editors", "canAdministerEditors"],
  ["can_administer_analysts", "canAdministerAnalysts"],
  ["can_administer_admins", "canAdministerAdmins"],
  ["can_read_conversations", "canReadConversations"],
  ["can_use_team_agents", "canUseTeamAgents"],
  ["can_use_team_applications", "canUseTeamApplications"],
  ["can_use_team_knowledge_bases", "canUseTeamKnowledgeBases"],
  ["can_access_files", "canAccessFiles"],
  ["can_run_evaluations", "canRunEvaluations"],
  ["can_manage_evaluation_corpus", "canManageEvaluationCorpus"],
  ["can_read_conversations_for_evaluation", "canReadConversationsForEvaluation"],
];

describe("mapTeamPermissions", () => {
  it("denies every flag for undefined, null, and an empty list", () => {
    for (const input of [undefined, null, []]) {
      const flags = mapTeamPermissions(input);
      expect(Object.values(flags).every((v) => v === false)).toBe(true);
    }
  });

  it.each(CASES)("turns exactly %s into %s, nothing else", (permission, flag) => {
    const flags = mapTeamPermissions([permission]);
    for (const [key, value] of Object.entries(flags)) {
      expect(value, `${key} for permission ${permission}`).toBe(key === flag);
    }
  });

  it("turns every known permission on at once for a team_admin-shaped response", () => {
    const allPermissions = CASES.map(([permission]) => permission);
    const flags = mapTeamPermissions(allPermissions);
    expect(Object.values(flags).every((v) => v === true)).toBe(true);
  });

  it("ignores an unknown permission string without throwing", () => {
    const flags = mapTeamPermissions(["not_a_real_permission" as TeamPermission]);
    expect(Object.values(flags).every((v) => v === false)).toBe(true);
  });
});

describe("canEditTeamContent", () => {
  const team = (...my_relations: UserTeamRelation[]) => ({ my_relations });

  it("grants a team_editor, alone or alongside other roles", () => {
    expect(canEditTeamContent(team("team_editor"))).toBe(true);
    expect(canEditTeamContent(team("team_member", "team_editor"))).toBe(true);
    expect(canEditTeamContent(team("team_admin", "team_editor"))).toBe(true);
  });

  // The whole point of this helper: `can_update_resources` resolves to
  // `team_editor` alone in schema.fga, so an admin-only caller must be
  // refused here exactly as the backend refuses them.
  it("refuses a team_admin who is not also an editor", () => {
    expect(canEditTeamContent(team("team_admin"))).toBe(false);
    expect(canEditTeamContent(team("pending_team_admin"))).toBe(false);
  });

  it("refuses every non-writing role", () => {
    for (const role of ["team_member", "team_analyst"] as UserTeamRelation[]) {
      expect(canEditTeamContent(team(role)), role).toBe(false);
    }
  });

  it("refuses a team whose relations are missing, null, or empty", () => {
    expect(canEditTeamContent({})).toBe(false);
    expect(canEditTeamContent({ my_relations: null })).toBe(false);
    expect(canEditTeamContent(team())).toBe(false);
  });
});
