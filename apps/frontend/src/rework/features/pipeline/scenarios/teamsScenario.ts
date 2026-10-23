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

import type { TeamPermission, UserTeamRelation } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { SELF_TEST_AGENT_ID } from "./corpus";
import { cleanup, expectRefused, newRunScope } from "./runScope";

export interface TeamsDeps {
  userId: string;
  personalTeamId: string;
  charterAccepted: () => Promise<boolean>;
  createTeam: (name: string, description: string, adminId: string) => Promise<{ id: string; relations: string[] }>;
  readTeam: (teamId: string) => Promise<{ permissions: TeamPermission[] }>;
  grantRole: (teamId: string, userId: string, relation: UserTeamRelation) => Promise<void>;
  revokeRole: (teamId: string, userId: string, relation: UserTeamRelation) => Promise<void>;
  createPrompt: (teamId: string, name: string) => Promise<string>;
  readPrompt: (teamId: string, promptId: string) => Promise<void>;
  deletePrompt: (teamId: string, promptId: string) => Promise<void>;
  createLibrary: (teamId: string, name: string) => Promise<string>;
  /** Folders visible in one team, or everywhere when `teamId` is null. */
  listLibraryIds: (teamId: string | null) => Promise<string[]>;
  deleteLibrary: (libraryId: string) => Promise<void>;
  provisionAgent: (teamId: string, sourceAgentId: string, name: string) => Promise<string | null>;
  listAgentIds: (teamId: string) => Promise<string[]>;
  copyAgent: (teamId: string, agentId: string, targetTeamId: string) => Promise<string | null>;
  deleteAgent: (teamId: string, agentId: string) => Promise<void>;
  wikiEnabled: (teamId: string) => Promise<boolean>;
  createWikiPage: (
    teamId: string,
    title: string,
    content: string,
  ) => Promise<{ pageId: string; slug: string; revisionId: string | null }>;
  /** Writes over `baseRevisionId`, the revision the caller last read. */
  writeWikiPage: (teamId: string, pageId: string, content: string, baseRevisionId: string | null) => Promise<void>;
  wikiRevisions: (teamId: string, pageId: string) => Promise<string[]>;
  restoreWikiRevision: (teamId: string, pageId: string, revisionId: string) => Promise<void>;
  readWikiPage: (teamId: string, slug: string) => Promise<string>;
  deleteWikiPage: (teamId: string, pageId: string) => Promise<void>;
  setJoinLink: (teamId: string, enabled: boolean) => Promise<{ enabled: boolean; token: string | null }>;
  regenerateJoinLink: (teamId: string) => Promise<string | null>;
  modelProfileCount: (teamId: string) => Promise<number>;
  readRoutingPolicy: (teamId: string) => Promise<void>;
  deleteTeam: (teamId: string) => Promise<void>;
}

/**
 * Teams family, in a disposable team the admin creates and administers. A
 * platform admin has no relation on any team, so this is the only way to
 * exercise team behavior as one person. The charter is never accepted here.
 */
export const teamsScenario: Scenario<TeamsDeps> = async (deps, report) => {
  const scope = newRunScope();
  const accepted = await runStep(report, "charter", "You accepted the team-admin charter", async () => {
    if (!(await deps.charterAccepted())) {
      throw new SkipStep("accept the team-admin charter first; the self-test never accepts it for you");
    }
    return { value: true, detail: "accepted" };
  });
  if (!accepted) return;

  let teamId: string | null = null;
  let promptId: string | null = null;
  let libraryId: string | null = null;
  let agentId: string | null = null;
  let personalCopy: string | null = null;
  let teamDeleted = false;
  const need = (): string => {
    if (!teamId) throw new SkipStep("the disposable team was not created");
    return teamId;
  };
  const writeRefused = async (id: string) => {
    const status = await expectRefused(
      () => deps.createPrompt(id, scope.name("fred-selftest-denied")),
      "creating a prompt",
    );
    if (status !== 403) throw new Error(`a refused write answered HTTP ${status}, expected 403`);
    return status;
  };

  try {
    await runStep(report, "create-team", "Create a disposable team you administer", async () => {
      const team = await deps.createTeam(
        scope.name("selftest"),
        "Disposable team created by the admin self-test; deleted at the end of the run.",
        deps.userId,
      );
      teamId = team.id;
      if (!team.relations.includes("team_admin"))
        throw new Error(`your relations are ${team.relations.join(", ") || "none"}`);
      return { value: team.id, detail: team.id };
    });
    await runStep(report, "admin-permissions", "Team admin alone administers but cannot edit content", async () => {
      const { permissions } = await deps.readTeam(need());
      for (const p of ["can_update_info", "can_administer_members", "can_administer_editors"] as const) {
        if (!permissions.includes(p)) throw new Error(`team admin lacks ${p}`);
      }
      if (permissions.includes("can_update_resources"))
        throw new Error("team admin can edit content without the editor role");
      const status = await writeRefused(need());
      return { value: undefined, detail: `content write refused with HTTP ${status}` };
    });
    await runStep(report, "grant-editor", "Granting yourself the editor role opens content editing", async () => {
      const id = need();
      await deps.grantRole(id, deps.userId, "team_editor");
      const { permissions } = await deps.readTeam(id);
      for (const p of ["can_update_resources", "can_update_agents"] as const) {
        if (!permissions.includes(p)) throw new Error(`the editor role did not grant ${p}`);
      }
      return { value: undefined, detail: "can_update_resources, can_update_agents" };
    });
    await runStep(report, "team-prompt", "A team prompt can be created and read", async () => {
      const id = need();
      const created = await deps.createPrompt(id, scope.name("fred-selftest-team-prompt"));
      promptId = created;
      await deps.readPrompt(id, created);
      return { value: created, detail: created };
    });
    await runStep(report, "team-library", "A team folder can be created and is listed", async () => {
      const id = need();
      const created = await deps.createLibrary(id, scope.name("fred-selftest-team-folder"));
      libraryId = created;
      if (!(await deps.listLibraryIds(id)).includes(created)) throw new Error("the team folder is not listed");
      return { value: created, detail: created };
    });
    await runStep(report, "team-agent", "The self-test agent can be enrolled in the team", async () => {
      const id = need();
      const created = await deps.provisionAgent(id, SELF_TEST_AGENT_ID, scope.name("Self-test (auto)"));
      if (!created) throw new SkipStep(`'${SELF_TEST_AGENT_ID}' is not enabled for new teams on this deployment`);
      agentId = created;
      if (!(await deps.listAgentIds(id)).includes(created)) throw new Error("the team agent is not listed");
      return { value: created, detail: created };
    });
    await runStep(report, "wiki", "The team wiki keeps revisions and restores one", async () => {
      const id = need();
      if (!(await deps.wikiEnabled(id))) throw new SkipStep("the team wiki is not enabled on this deployment");
      const first = scope.name("Selftestwikifirst");
      const page = await deps.createWikiPage(id, scope.name("Self-test page"), `First version: ${first}`);
      try {
        await deps.writeWikiPage(id, page.pageId, "Second version without the marker", page.revisionId);
        const revisions = await deps.wikiRevisions(id, page.pageId);
        if (revisions.length < 2) throw new Error(`${revisions.length} revision(s) after two writes`);
        // Revisions are listed newest first; the oldest one holds the marker.
        await deps.restoreWikiRevision(id, page.pageId, revisions[revisions.length - 1]);
        if (!(await deps.readWikiPage(id, page.slug)).includes(first))
          throw new Error("the restored page lost its first version");
      } finally {
        await deps.deleteWikiPage(id, page.pageId);
      }
      return { value: undefined, detail: "written twice, restored, deleted" };
    });
    await runStep(report, "join-link", "The join link can be opened, rotated and closed", async () => {
      const id = need();
      const opened = await deps.setJoinLink(id, true);
      if (!opened.enabled || !opened.token) throw new Error("opening the join link gave no token");
      try {
        const rotated = await deps.regenerateJoinLink(id);
        if (!rotated || rotated === opened.token) throw new Error("rotating the join link kept the same token");
      } finally {
        const closed = await deps.setJoinLink(id, false);
        if (closed.enabled) throw new Error("the join link stayed open");
      }
      return { value: undefined, detail: "opened, rotated, closed" };
    });
    await runStep(report, "routing", "The team's model routing can be read", async () => {
      const id = need();
      await deps.readRoutingPolicy(id);
      const profiles = await deps.modelProfileCount(id);
      if (profiles === 0) throw new Error("no model profile is offered to the new team");
      return { value: undefined, detail: `${profiles} profile(s)` };
    });
    await runStep(report, "copy-to-personal", "The team agent can be copied to your personal space", async () => {
      if (!agentId) throw new SkipStep("no team agent");
      const copy = await deps.copyAgent(need(), agentId, deps.personalTeamId);
      if (!copy) throw new Error("the copy was refused");
      personalCopy = copy;
      if (!(await deps.listAgentIds(deps.personalTeamId)).includes(copy))
        throw new Error("the copy is not in your personal space");
      return { value: copy, detail: copy };
    });
    await runStep(report, "revoke-editor", "Revoking your editor role closes content editing again", async () => {
      const id = need();
      await deps.revokeRole(id, deps.userId, "team_editor");
      const status = await writeRefused(id);
      return { value: undefined, detail: `refused with HTTP ${status}` };
    });
  } finally {
    await cleanup(
      report,
      "delete-personal-copy",
      "Delete the personal copy",
      personalCopy,
      (id) => deps.deleteAgent(deps.personalTeamId, id),
      async (id) => {
        if ((await deps.listAgentIds(deps.personalTeamId)).includes(id))
          throw new Error(`personal agent ${id} is still listed after deletion`);
      },
    );
    const team = teamId;
    if (team) {
      await deps.grantRole(team, deps.userId, "team_editor").catch(() => undefined);
      await cleanup(
        report,
        "delete-team-prompt",
        "Delete the team prompt",
        promptId,
        (id) => deps.deletePrompt(team, id),
        async (id) => {
          await expectRefused(() => deps.readPrompt(team, id), "reading the deleted prompt", [404]);
        },
      );
      await cleanup(
        report,
        "delete-team-folder",
        "Delete the team folder",
        libraryId,
        deps.deleteLibrary,
        async (id) => {
          if ((await deps.listLibraryIds(null)).includes(id))
            throw new Error(`folder ${id} is still listed after deletion`);
        },
      );
    }
    await cleanup(
      report,
      "delete-team",
      "Delete the disposable team",
      teamId,
      async (id) => {
        await deps.deleteTeam(id);
        teamDeleted = true;
      },
      async (id) => {
        await expectRefused(() => deps.readTeam(id), "reading the deleted team", [404]);
      },
    );
  }
  await runStep(
    report,
    "team-gone",
    "Nothing of the deleted team stays reachable",
    async () => {
      if (!teamId || !teamDeleted) throw new SkipStep("the team was not deleted");
      const id = teamId;
      await expectRefused(() => deps.readTeam(id), "reading the deleted team");
      await expectRefused(() => deps.listAgentIds(id), "listing the deleted team's agents");
      if (promptId) await expectRefused(() => deps.readPrompt(id, promptId!), "reading the deleted team's prompt");
      if (libraryId && (await deps.listLibraryIds(null)).includes(libraryId)) {
        throw new Error("the team folder is still listed");
      }
      if (personalCopy && (await deps.listAgentIds(deps.personalTeamId)).includes(personalCopy)) {
        throw new Error("the personal agent copy is still listed");
      }
      return { value: undefined, detail: "team, agents, prompt, folder and personal copy unreachable" };
    },
    { optional: true },
  );
};
