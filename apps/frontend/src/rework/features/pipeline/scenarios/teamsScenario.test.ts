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

import { describe, expect, it } from "vitest";
import type { TeamPermission, UserTeamRelation } from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { collect, signal } from "./fakePlatform";
import { teamsScenario, type TeamsDeps } from "./teamsScenario";

const ME = "admin-uid";
const PERSONAL = `personal-${ME}`;
const refused = (status: number) => Object.assign(new Error(`HTTP ${status}`), { status });

/** In-memory teams: roles decide what a write may do. */
class FakeTeams {
  charter = true;
  wiki = true;
  editorGate = true;
  teams = new Map<string, Set<UserTeamRelation>>();
  prompts = new Map<string, string>();
  libraries = new Map<string, string>();
  agents = new Map<string, string>([["personal-agent", PERSONAL]]);
  pages = new Map<string, string[]>();
  joinToken = 0;
  private next = 0;

  id(prefix: string) {
    this.next += 1;
    return `${prefix}-${this.next}`;
  }

  roles(teamId: string) {
    const roles = this.teams.get(teamId);
    if (!roles) throw refused(404);
    return roles;
  }

  permissions(teamId: string): TeamPermission[] {
    const roles = this.roles(teamId);
    const out: TeamPermission[] = ["can_read"];
    if (roles.has("team_admin")) out.push("can_update_info", "can_administer_members", "can_administer_editors");
    if (roles.has("team_editor") || !this.editorGate) out.push("can_update_resources", "can_update_agents");
    return out;
  }

  editor(teamId: string) {
    if (this.editorGate && !this.roles(teamId).has("team_editor")) throw refused(403);
  }

  deps(): TeamsDeps {
    return {
      userId: ME,
      personalTeamId: PERSONAL,
      charterAccepted: async () => this.charter,
      createTeam: async () => {
        const id = this.id("team");
        this.teams.set(id, new Set<UserTeamRelation>(["team_admin"]));
        return { id, relations: ["team_admin"] };
      },
      readTeam: async (teamId) => ({ permissions: this.permissions(teamId) }),
      grantRole: async (teamId, _user, relation) => {
        this.roles(teamId).add(relation);
      },
      revokeRole: async (teamId, _user, relation) => {
        this.roles(teamId).delete(relation);
      },
      createPrompt: async (teamId) => {
        this.editor(teamId);
        const id = this.id("prompt");
        this.prompts.set(id, teamId);
        return id;
      },
      readPrompt: async (teamId, promptId) => {
        this.roles(teamId);
        if (this.prompts.get(promptId) !== teamId) throw refused(404);
      },
      deletePrompt: async (teamId, promptId) => {
        this.editor(teamId);
        this.prompts.delete(promptId);
      },
      createLibrary: async (teamId) => {
        this.editor(teamId);
        const id = this.id("folder");
        this.libraries.set(id, teamId);
        return id;
      },
      listLibraryIds: async (teamId) =>
        [...this.libraries].filter(([, t]) => (teamId ? t === teamId : this.teams.has(t))).map(([id]) => id),
      deleteLibrary: async (id) => {
        this.libraries.delete(id);
      },
      provisionAgent: async (teamId) => {
        this.editor(teamId);
        const id = this.id("agent");
        this.agents.set(id, teamId);
        return id;
      },
      listAgentIds: async (teamId) => {
        if (teamId !== PERSONAL) this.roles(teamId);
        return [...this.agents].filter(([, t]) => t === teamId).map(([id]) => id);
      },
      copyAgent: async (_teamId, _agentId, target) => {
        const id = this.id("agent");
        this.agents.set(id, target);
        return id;
      },
      deleteAgent: async (_teamId, id) => {
        this.agents.delete(id);
      },
      wikiEnabled: async () => this.wiki,
      createWikiPage: async (_teamId, _title, content) => {
        const id = this.id("page");
        this.pages.set(id, [content]);
        return { pageId: id, slug: id, revisionId: "r0" };
      },
      writeWikiPage: async (_teamId, pageId, content, base) => {
        if (!base) throw refused(409);
        this.pages.get(pageId)!.push(content);
      },
      wikiRevisions: async (_teamId, pageId) =>
        this.pages
          .get(pageId)!
          .map((_, i) => `r${i}`)
          .reverse(),
      restoreWikiRevision: async (_teamId, pageId, revisionId) => {
        const versions = this.pages.get(pageId)!;
        versions.push(versions[Number(revisionId.slice(1))]);
      },
      readWikiPage: async (_teamId, slug) => {
        const versions = this.pages.get(slug);
        if (!versions) throw refused(404);
        return versions[versions.length - 1];
      },
      deleteWikiPage: async (_teamId, pageId) => {
        this.pages.delete(pageId);
      },
      setJoinLink: async (_teamId, enabled) => ({ enabled, token: enabled ? `t${++this.joinToken}` : null }),
      regenerateJoinLink: async () => `t${++this.joinToken}`,
      modelProfileCount: async () => 1,
      readRoutingPolicy: async () => {},
      deleteTeam: async (teamId) => {
        this.teams.delete(teamId);
        for (const [id, t] of this.agents) if (t === teamId) this.agents.delete(id);
      },
    };
  }
}

async function run(fake: FakeTeams, deps = fake.deps()) {
  const r = collect();
  await teamsScenario(deps, r.report, signal);
  return r;
}

describe("teamsScenario", () => {
  it("passes every check and leaves no team, prompt, folder, page or copy", async () => {
    const fake = new FakeTeams();
    const r = await run(fake);
    expect(r.steps.filter((s) => s.status !== "passed").map((s) => `${s.id}:${s.status}`)).toEqual([]);
    expect([fake.teams.size, fake.prompts.size, fake.libraries.size, fake.pages.size]).toEqual([0, 0, 0, 0]);
    expect([...fake.agents.keys()]).toEqual(["personal-agent"]);
  });

  it("uses the team run token in the enrolled agent name", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    const createTeam = deps.createTeam;
    let teamName = "";
    let agentName = "";
    deps.createTeam = async (name, description, adminId) => {
      teamName = name;
      return createTeam(name, description, adminId);
    };
    const provision = deps.provisionAgent;
    deps.provisionAgent = async (teamId, sourceId, name) => {
      agentName = name;
      return provision(teamId, sourceId, name);
    };
    await run(fake, deps);
    expect(agentName).toContain(teamName.slice(-8));
  });

  it("creates nothing without an accepted charter", async () => {
    const fake = new FakeTeams();
    fake.charter = false;
    const r = await run(fake);
    expect(r.status("charter")).toBe("skipped");
    expect(r.steps).toHaveLength(1);
    expect(fake.teams.size).toBe(0);
  });

  it("deletes a team even when its creation response lacks the admin relation", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    const create = deps.createTeam;
    deps.createTeam = async (name, description, adminId) => ({
      ...(await create(name, description, adminId)),
      relations: [],
    });
    const r = await run(fake, deps);
    expect(r.status("create-team")).toBe("failed");
    expect(r.status("delete-team")).toBe("passed");
    expect(fake.teams.size).toBe(0);
  });

  it("deletes a personal copy even when its listing check fails", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    const list = deps.listAgentIds;
    let personalReads = 0;
    deps.listAgentIds = async (teamId) => {
      if (teamId === PERSONAL && ++personalReads === 1) return [];
      return list(teamId);
    };
    const r = await run(fake, deps);
    expect(r.status("copy-to-personal")).toBe("failed");
    expect(r.status("delete-personal-copy")).toBe("passed");
    expect([...fake.agents.keys()]).toEqual(["personal-agent"]);
  });

  it("reports a personal copy that survives deletion", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    deps.deleteAgent = async () => {};
    const r = await run(fake, deps);
    expect(r.status("team-gone")).toBe("failed");
  });

  it("fails when team admin alone can edit content", async () => {
    const fake = new FakeTeams();
    fake.editorGate = false;
    expect((await run(fake)).status("admin-permissions")).toBe("failed");
  });

  it("fails when revoking the editor role leaves writes open", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    deps.revokeRole = async () => {};
    expect((await run(fake, deps)).status("revoke-editor")).toBe("failed");
  });

  it("skips the wiki when it is off, and fails a restore that loses the first version", async () => {
    const off = new FakeTeams();
    off.wiki = false;
    expect((await run(off)).status("wiki")).toBe("skipped");
    const broken = new FakeTeams();
    const deps = broken.deps();
    deps.restoreWikiRevision = async () => {};
    expect((await run(broken, deps)).status("wiki")).toBe("failed");
    expect(broken.pages.size).toBe(0);
  });

  it("fails the wiki check when deletion leaves the page readable", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    deps.deleteWikiPage = async () => {};
    const r = await run(fake, deps);
    expect(r.status("wiki")).toBe("failed");
  });

  it("fails a join link that keeps its token when rotated, and closes it anyway", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    let closed = false;
    deps.regenerateJoinLink = async () => "t1";
    const set = deps.setJoinLink;
    deps.setJoinLink = async (id, enabled) => {
      if (!enabled) closed = true;
      return set(id, enabled);
    };
    expect((await run(fake, deps)).status("join-link")).toBe("failed");
    expect(closed).toBe(true);
  });

  it("reports team agents that survive the team's deletion", async () => {
    const fake = new FakeTeams();
    const deps = fake.deps();
    deps.deleteTeam = async (id) => {
      fake.teams.delete(id);
      deps.listAgentIds = async () => ["survivor"];
    };
    const r = await run(fake, deps);
    expect(r.status("team-gone")).toBe("failed");
  });
});
