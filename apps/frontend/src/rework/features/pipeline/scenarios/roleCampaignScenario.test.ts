// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
import { describe, expect, it } from "vitest";
import type { PlatformRoleRelation, UserTeamRelation } from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { collect } from "./fakePlatform";
import {
  recoverRoleCampaign,
  roleCampaignScenario,
  CAMPAIGN_PLATFORM_CASES,
  campaignTeamCases,
  type CampaignDeps,
  type CampaignJournal,
} from "./roleCampaignScenario";
import { PLATFORM_ROLES } from "./rolePermissions";
const ROLE_ROUTES: Array<{ id: string; path: string; roles: PlatformRoleRelation[] }> = [
  { id: "registry", path: "/teams/all", roles: ["team_manager", "feature_manager"] },
  { id: "team-creation", path: "/teams/candidate-admins?query=selftest", roles: ["team_manager"] },
  { id: "capabilities", path: "/admin/capabilities", roles: ["feature_manager"] },
  { id: "model-bindings", path: "/admin/platform/model-bindings", roles: ["feature_manager"] },
  { id: "platform-prompt", path: "/admin/platform/prompt", roles: ["prompt_editor"] },
  { id: "instructions", path: "/admin/platform/instructions", roles: ["prompt_editor"] },
  { id: "users", path: "/users", roles: [] },
  { id: "role-roster", path: "/users/platform-roles", roles: [] },
  { id: "ui-settings", path: "/admin/platform/ui-settings", roles: [] },
  { id: "announcements", path: "/admin/platform/announcements", roles: [] },
  { id: "import-export", path: "/import-export/stats", roles: [] },
  { id: "observation", path: "/kpi/presets/sessions_over_time", roles: ["platform_observer"] },
];

const CP = "/control-plane/v1",
  ADMIN = "admin-secret",
  TARGET = "target-secret";
type FakeTeam = { id: string; name: string; description: string; visibility: string; roles: UserTeamRelation[] };
function fake(
  options: { accepted?: boolean; root?: boolean; sameUser?: boolean; original?: PlatformRoleRelation[] } = {},
) {
  const state = {
    roles: [...(options.original ?? ["prompt_editor"])] as PlatformRoleRelation[],
    journal: null as CampaignJournal | null,
    teams: new Map<string, FakeTeam>(),
    prompts: new Map<string, { id: string; name: string; text: string; command: string }>(),
    calls: [] as Array<{ path: string; token: string; method: string; body: unknown }>,
    snapshots: [] as CampaignJournal[],
    platformSets: new Set<string>(),
    teamSets: new Set<string>(),
    inject: undefined as
      | undefined
      | ((path: string, token: string, method: string, body: unknown) => { status: number; body: unknown } | void),
  };
  let next = 0;
  const permissions = (roles: UserTeamRelation[], visibility: string) => [
    ...new Set([
      ...(roles.length
        ? [
            "can_read",
            "can_read_members",
            "can_read_conversations",
            "can_use_team_agents",
            "can_use_team_applications",
            "can_use_team_knowledge_bases",
            "can_access_files",
          ]
        : visibility === "public"
          ? ["can_read"]
          : []),
      ...(roles.includes("team_admin")
        ? [
            "can_update_info",
            "can_administer_members",
            "can_administer_editors",
            "can_administer_analysts",
            "can_administer_admins",
            "can_unpublish_marketplace_agents",
            "can_run_evaluations",
            "can_manage_evaluation_corpus",
          ]
        : []),
      ...(roles.includes("team_editor")
        ? [
            "can_update_resources",
            "can_update_agents",
            "can_publish_marketplace_agents",
            "can_unpublish_marketplace_agents",
          ]
        : []),
      ...(roles.includes("team_analyst")
        ? ["can_run_evaluations", "can_manage_evaluation_corpus", "can_read_conversations_for_evaluation"]
        : []),
    ]),
  ];
  const request: CampaignDeps["request"] = async (path, token, init) => {
    const method = init?.method ?? "GET";
    state.calls.push({ path, token, method, body: init?.body });
    const intercepted = state.inject?.(path, token, method, init?.body);
    if (intercepted) return intercepted;
    const route = new URL(path, "http://local").pathname.slice(CP.length),
      admin = token === ADMIN;
    if (route === "/frontend/bootstrap") {
      if (!admin) state.platformSets.add([...state.roles].sort().join(","));
      return {
        status: 200,
        body: {
          current_user: { id: admin || options.sameUser ? "root-user" : "test-user" },
          permissions: {
            platform_roles: admin || state.roles.includes("platform_admin") ? PLATFORM_ROLES : state.roles,
          },
          team_admin_charter_enabled: true,
        },
      };
    }
    if (route === "/team-admin-charter")
      return { status: 200, body: admin || options.accepted !== false ? { accepted_at: "2026-10-21" } : null };
    if (route === "/users/platform-roles" && admin)
      return {
        status: 200,
        body: {
          caller_is_bootstrap_root: options.root !== false,
          holders: [
            { user: { id: "root-user" }, relations: ["platform_admin"], is_bootstrap_root: true },
            ...(state.roles.length
              ? [{ user: { id: "test-user" }, relations: [...state.roles], is_bootstrap_root: false }]
              : []),
          ],
        },
      };
    if (route.startsWith("/users/test-user/platform-roles") && admin) {
      if (method === "POST")
        state.roles = [...new Set([...state.roles, (init?.body as { relation: PlatformRoleRelation }).relation])];
      if (method === "DELETE") state.roles = state.roles.filter((role) => role !== route.split("/").pop());
      return { status: 204, body: null };
    }
    if (route === "/teams/all" && admin) return { status: 200, body: [...state.teams.values()] };
    if (route === "/teams" && method === "GET")
      return { status: 200, body: [{ id: `personal-${admin ? "root-user" : "test-user"}`, is_member: true }] };
    if (route === "/teams" && method === "POST") {
      const id = `team-${++next}`,
        body = init!.body as { name: string; description: string };
      const team: FakeTeam = { ...body, id, visibility: "public", roles: [] };
      state.teams.set(id, team);
      return { status: 201, body: team };
    }
    if (route.startsWith("/teams/personal-")) {
      const owner = route.split("/")[2] === `personal-${admin ? "root-user" : "test-user"}`;
      if (!owner) return { status: 403, body: null };
      const base = `${CP}/teams/${route.split("/")[2]}/prompts/`;
      if (route.endsWith("/prompts") && method === "POST") {
        const prompt = { ...(init!.body as { name: string; text: string; command: string }), id: `p-${++next}` };
        state.prompts.set(base + prompt.id, prompt);
        return { status: 201, body: prompt };
      }
      if (path.startsWith(base) && !route.endsWith("/prompts/context")) {
        const prompt = state.prompts.get(path);
        if (method === "DELETE") {
          state.prompts.delete(path);
          return { status: 204, body: null };
        }
        return { status: prompt ? 200 : 404, body: prompt ?? null };
      }
      if (route.endsWith("/prompt-commands"))
        return {
          status: 200,
          body: [...state.prompts.entries()]
            .filter(([path]) => path.startsWith(base))
            .map(([, prompt]) => ({ command: prompt.command, prompt_id: prompt.id })),
        };
      return { status: 200, body: [] };
    }
    if (route.startsWith("/teams/team-")) {
      const [, , id, surface, member, rolesRoute, role] = route.split("/");
      const team = state.teams.get(id);
      if (!team) return { status: 404, body: null };
      if (!surface) {
        if (method === "DELETE") {
          state.teams.delete(id);
          return { status: 204, body: null };
        }
        if (method === "PATCH") {
          Object.assign(team, init!.body);
          return { status: 200, body: team };
        }
        const relations: UserTeamRelation[] = admin ? ["team_admin", "team_editor"] : team.roles;
        if (!admin) state.teamSets.add(`${team.visibility}:${[...relations].sort().join(",")}`);
        return {
          status: admin || team.roles.length || team.visibility === "public" ? 200 : 403,
          body: {
            ...team,
            my_relations: relations,
            is_member: !!relations.length,
            permissions: permissions(relations, team.visibility),
          },
        };
      }
      if (surface === "members" && admin) {
        if (method === "POST") {
          const body = init!.body as { user_id: string; relation: UserTeamRelation };
          if (body.relation === "pending_team_admin") return { status: 422, body: null };
          if (body.user_id === "test-user")
            team.roles = [
              ...new Set<UserTeamRelation>([
                ...team.roles,
                body.relation === "team_admin" && options.accepted === false ? "pending_team_admin" : body.relation,
              ]),
            ];
          return { status: 204, body: null };
        }
        if (method === "DELETE") {
          team.roles = rolesRoute === "roles" ? team.roles.filter((r) => r !== role) : [];
          return { status: rolesRoute === "roles" ? 204 : 202, body: null };
        }
        return { status: 200, body: team.roles.length ? [{ user: { id: "test-user" }, relations: team.roles }] : [] };
      }
      const allowed = admin || team.roles.length > 0,
        base = `${CP}/teams/${id}/prompts/`;
      if (surface === "prompts" && method === "POST") {
        if (!admin && !team.roles.includes("team_editor")) return { status: 403, body: null };
        const prompt = { ...(init!.body as { name: string; text: string; command: string }), id: `p-${++next}` };
        state.prompts.set(base + prompt.id, prompt);
        return { status: 201, body: prompt };
      }
      if (surface === "prompts" && member) {
        if (!allowed) return { status: 403, body: null };
        const prompt = state.prompts.get(path);
        if (method === "DELETE") {
          state.prompts.delete(path);
          return { status: 204, body: null };
        }
        return { status: prompt ? 200 : 404, body: prompt ?? null };
      }
      if (surface === "prompt-commands")
        return {
          status: allowed ? 200 : 403,
          body: [...state.prompts.entries()]
            .filter(([path]) => path.startsWith(base))
            .map(([, p]) => ({ command: p.command, prompt_id: p.id })),
        };
      return { status: allowed ? 200 : 403, body: [] };
    }
    const gate = ROLE_ROUTES.find((r) => r.path.split("?")[0] === route);
    if (gate)
      return {
        status:
          admin || state.roles.includes("platform_admin") || gate.roles.some((role) => state.roles.includes(role))
            ? 200
            : 403,
        body: [],
      };
    return { status: 404, body: null };
  };
  const deps: CampaignDeps = {
    request,
    readJournal: () => (state.journal ? structuredClone(state.journal) : null),
    saveJournal: (journal) => {
      state.journal = journal ? structuredClone(journal) : null;
      if (journal) state.snapshots.push(structuredClone(journal));
    },
  };
  return { state, deps };
}
async function run(f: ReturnType<typeof fake>, signal?: AbortSignal) {
  const c = collect();
  await roleCampaignScenario(ADMIN, TARGET, f.deps, c.report, signal);
  return c.steps.filter((s) => s.status !== "running");
}

describe("automatic two-account role campaign", () => {
  it.each([true, false])("exercises the matrix, accepted charter=%s and restores grants", async (accepted) => {
    const f = fake({ accepted, original: ["team_manager", "platform_observer"] }),
      steps = await run(f);
    expect(steps.filter((s) => s.status === "failed")).toEqual([]);
    expect(steps.filter((s) => /^platform-\d+-roles$/.test(s.id))).toHaveLength(6);
    expect(steps.filter((s) => /^team-\d+.*-roles$/.test(s.id))).toHaveLength(12);
    expect(steps.length).toBe(148);
    expect(f.state.calls.length).toBeLessThanOrEqual(500);
    for (const roles of CAMPAIGN_PLATFORM_CASES)
      expect(f.state.platformSets.has([...roles].sort().join(","))).toBe(true);
    for (const visibility of ["public", "private"])
      for (const roles of campaignTeamCases(accepted ? "team_admin" : "pending_team_admin"))
        expect(f.state.teamSets.has(`${visibility}:${[...roles].sort().join(",")}`)).toBe(true);
    expect(f.state.roles.sort()).toEqual(["platform_observer", "team_manager"]);
    expect(f.state.teams.size).toBe(0);
    expect(f.state.prompts.size).toBe(0);
    expect(f.state.journal).toBeNull();
    expect(JSON.stringify(f.state.snapshots)).not.toMatch(/admin-secret|target-secret/);
    expect(f.state.calls.filter((c) => c.path.includes("personal-test-user") && c.method !== "GET")).toEqual([]);
    expect(f.state.calls.filter((c) => c.path.startsWith(`${CP}/users/root-user`) && c.method !== "GET")).toEqual([]);
    expect(
      steps.filter((s) => s.id.startsWith("revoked-") && s.id.endsWith("-write")).every((s) => s.status === "passed"),
    ).toBe(true);
  });
  it.each([{ root: false }, { sameUser: true }])("refuses unsafe preflight %j without writes", async (options) => {
    const f = fake(options);
    expect((await run(f)).some((s) => s.id === "campaign-preflight" && s.status === "failed")).toBe(true);
    expect(f.state.calls.filter((c) => c.method !== "GET")).toEqual([]);
  });
  it("does not overwrite an unfinished journal", async () => {
    const f = fake();
    f.state.journal = {
      version: 1,
      adminId: "root-user",
      targetId: "test-user",
      originalRoles: [],
      scope: "prior",
      teamNames: [],
      prompts: [],
    };
    await run(f);
    expect(f.state.calls).toEqual([]);
    expect(f.state.journal?.scope).toBe("prior");
  });
  it.each([401, 403, 500])("target HTTP %i stops mutation and restores grants", async (status) => {
    const f = fake();
    let reads = 0;
    f.state.inject = (path, token) => {
      if (path.endsWith("/frontend/bootstrap") && token === TARGET && ++reads > 4) return { status, body: null };
    };
    const steps = await run(f);
    expect(steps.some((s) => s.id === "campaign-interrupted" && s.status === "failed")).toBe(true);
    expect(f.state.roles).toEqual(["prompt_editor"]);
    expect(f.state.journal).toBeNull();
  });
  it("restores after cancellation", async () => {
    const f = fake(),
      controller = new AbortController();
    f.state.inject = (_path, _token, method) => {
      if (method === "POST") controller.abort();
    };
    expect((await run(f, controller.signal)).some((s) => s.id === "campaign-interrupted")).toBe(true);
    expect(f.state.roles).toEqual(["prompt_editor"]);
    expect(f.state.journal).toBeNull();
  });
  it("recovers creation persisted before a lost response", async () => {
    const f = fake(),
      base = f.deps.request;
    f.deps.request = async (...args) => {
      const response = await base(...args);
      if (args[0] === `${CP}/teams` && args[2]?.method === "POST") throw new Error("lost response");
      return response;
    };
    expect((await run(f)).some((s) => s.id === "campaign-interrupted")).toBe(true);
    expect(f.state.teams.size).toBe(0);
    expect(f.state.roles).toEqual(["prompt_editor"]);
    expect(f.state.journal).toBeNull();
  });
  it("journals prompts before POST and retries failed cleanup before team deletion", async () => {
    const f = fake();
    let refuseDelete = true;
    f.state.inject = (path, _token, method, body) => {
      if (path.endsWith("/prompts") && method === "POST")
        expect(f.state.journal?.prompts.some((p) => p.name === (body as { name: string }).name)).toBe(true);
      if (path.includes("/prompts/") && method === "DELETE" && refuseDelete) return { status: 500, body: null };
    };
    expect((await run(f)).some((s) => s.id === "campaign-restored" && s.status === "failed")).toBe(true);
    expect(f.state.journal).not.toBeNull();
    expect(f.state.prompts.size).toBeGreaterThan(0);
    refuseDelete = false;
    const c = collect();
    await recoverRoleCampaign(ADMIN, f.deps, c.report);
    expect(c.steps.filter((s) => s.status === "failed")).toEqual([]);
    expect(f.state.journal).toBeNull();
    expect(f.state.prompts.size).toBe(0);
    expect(f.state.teams.size).toBe(0);
  });
  it("keeps evidence when a platform role cannot be restored", async () => {
    const f = fake();
    let phase = false;
    f.state.inject = (path, _token, method, body) => {
      if (path.endsWith("/members") && method === "POST" && (body as { user_id: string }).user_id === "test-user") {
        phase = true;
        return { status: 500, body: null };
      }
      if (phase && path === `${CP}/users/test-user/platform-roles` && method === "POST")
        return { status: 500, body: null };
    };
    await run(f);
    expect(f.state.journal?.originalRoles).toEqual(["prompt_editor"]);
    f.state.inject = undefined;
    const c = collect();
    await recoverRoleCampaign(ADMIN, f.deps, c.report);
    expect(f.state.roles).toEqual(["prompt_editor"]);
    expect(f.state.journal).toBeNull();
  });
  it("rejects a forged journal without writes", async () => {
    const f = fake();
    f.state.journal = {
      version: 1,
      adminId: "root-user",
      targetId: "test-user",
      originalRoles: [],
      scope: "test",
      teamNames: ["existing-team"],
      prompts: [],
    };
    const c = collect();
    await recoverRoleCampaign(ADMIN, f.deps, c.report);
    expect(c.steps.some((s) => s.status === "failed")).toBe(true);
    expect(f.state.calls.filter((c) => c.method !== "GET")).toEqual([]);
  });
  it("requires journal storage before the first mutation", async () => {
    const f = fake();
    f.deps.saveJournal = () => {
      throw new Error("Storage disabled");
    };
    expect((await run(f)).some((s) => s.status === "failed")).toBe(true);
    expect(f.state.calls.filter((c) => c.method !== "GET")).toEqual([]);
  });
  it.each([
    [1, "/users"],
    [2, "/kpi/presets/sessions_over_time"],
    [3, "/teams/all"],
    [4, "/admin/capabilities"],
    [5, "/admin/platform/prompt"],
  ] as const)("detects unexpected denial for platform case %i", async (index, route) => {
    const f = fake();
    f.state.inject = (path, token) => {
      if (token === TARGET && new URL(path, "http://local").pathname === `${CP}${route}`)
        return { status: 403, body: null };
    };
    const steps = await run(f);
    expect(steps.some((step) => step.id === `platform-${index}-access` && step.status === "failed")).toBe(true);
    expect(f.state.roles).toEqual(["prompt_editor"]);
    expect(f.state.journal).toBeNull();
  });
  it("cleans a prompt persisted before a refused response", async () => {
    const f = fake(),
      base = f.deps.request;
    f.deps.request = async (...args) => {
      const response = await base(...args);
      if (args[2]?.method === "POST" && args[0].endsWith("/prompts") && response.status === 201)
        return { status: 403, body: null };
      return response;
    };
    expect((await run(f)).some((step) => step.id.endsWith("-write") && step.status === "failed")).toBe(true);
    expect(f.state.prompts.size).toBe(0);
    expect(f.state.teams.size).toBe(0);
    expect(f.state.journal).toBeNull();
  });
  it("does not repeat successful partial team deletion during recovery", async () => {
    const f = fake();
    let refuse = true;
    f.state.inject = (path, _token, method) => {
      if (method === "DELETE" && path === `${CP}/teams/team-1` && refuse) return { status: 500, body: null };
    };
    await run(f);
    expect(f.state.journal?.teamNames).toHaveLength(1);
    expect(f.state.teams.size).toBe(1);
    refuse = false;
    const c = collect();
    await recoverRoleCampaign(ADMIN, f.deps, c.report);
    expect(c.steps.filter((s) => s.status === "failed")).toEqual([]);
    expect(f.state.journal).toBeNull();
  });
  it("requires the admin charter without accepting it automatically", async () => {
    const f = fake();
    f.state.inject = (path, token) => {
      if (path.endsWith("/team-admin-charter") && token === ADMIN) return { status: 200, body: null };
    };
    expect((await run(f)).some((step) => step.id === "campaign-preflight" && step.status === "failed")).toBe(true);
    expect(f.state.calls.filter((c) => c.method !== "GET")).toEqual([]);
  });
  it("refuses recovery as another root identity", async () => {
    const f = fake();
    f.state.journal = {
      version: 1,
      adminId: "another-root",
      targetId: "test-user",
      originalRoles: [],
      scope: "prior",
      teamNames: [],
      prompts: [],
    };
    const c = collect();
    await recoverRoleCampaign(ADMIN, f.deps, c.report);
    expect(c.steps.some((step) => step.status === "failed")).toBe(true);
    expect(f.state.calls.filter((c) => c.method !== "GET")).toEqual([]);
    expect(f.state.journal).not.toBeNull();
  });
  it("detects cross-team content leakage even for a platform administrator", async () => {
    const f = fake();
    f.state.inject = (path, token, method) => {
      if (token === TARGET && method === "GET" && /^\/control-plane\/v1\/teams\/team-[^/]+\/prompts$/.test(path))
        return { status: 200, body: [] };
    };
    const steps = await run(f);
    expect(steps.some((step) => step.id === "admin-no-team-private" && step.status === "failed")).toBe(true);
    expect(steps.some((step) => step.id.endsWith("-other-content") && step.status === "failed")).toBe(true);
    expect(f.state.journal).toBeNull();
    expect(f.state.roles).toEqual(["prompt_editor"]);
  });
  it("detects a platform administrator reading the other user's private prompts", async () => {
    const f = fake();
    f.state.inject = (path, token) => {
      if (token === ADMIN && path === `${CP}/teams/personal-test-user/prompts`) return { status: 200, body: [] };
    };
    expect((await run(f)).some((step) => step.id === "personal-isolation-/prompts" && step.status === "failed")).toBe(
      true,
    );
    expect(f.state.journal).toBeNull();
  });
  it("stops and restores when a role projection grants unexpected permissions", async () => {
    const f = fake(),
      base = f.deps.request;
    f.deps.request = async (...args) => {
      const response = await base(...args);
      if (args[1] === TARGET && /^\/control-plane\/v1\/teams\/team-[^/]+$/.test(args[0]) && response.status === 200) {
        const body = response.body as { permissions: string[] };
        return { ...response, body: { ...body, permissions: [...body.permissions, "can_update_resources"] } };
      }
      return response;
    };
    expect((await run(f)).some((step) => step.id === "campaign-interrupted" && step.status === "failed")).toBe(true);
    expect(f.state.journal).toBeNull();
    expect(f.state.roles).toEqual(["prompt_editor"]);
  });
  it("keeps an exact admin personal prompt private and cleans it after a leaked read", async () => {
    const f = fake();
    f.state.inject = (path, token) => {
      if (token === TARGET && path.startsWith(`${CP}/teams/personal-root-user/prompts/`) && !path.endsWith("/context"))
        return { status: 200, body: {} };
    };
    const steps = await run(f);
    expect(steps.some((s) => s.id === "personal-exact-prompt" && s.status === "failed")).toBe(true);
    expect(f.state.prompts.size).toBe(0);
    expect(f.state.journal).toBeNull();
  });
  it("recovers a foreign write persisted in the administrator's personal space despite refusal", async () => {
    const f = fake(),
      base = f.deps.request;
    f.deps.request = async (...args) => {
      if (args[1] === TARGET && args[0] === `${CP}/teams/personal-root-user/prompts` && args[2]?.method === "POST") {
        await base(args[0], ADMIN, args[2]);
        return { status: 403, body: null };
      }
      return base(...args);
    };
    const steps = await run(f);
    expect(steps.some((s) => s.id === "personal-foreign-write" && s.status === "failed")).toBe(true);
    expect(f.state.prompts.size).toBe(0);
    expect(f.state.journal).toBeNull();
  });
  it.each([401, 429, 500])("rejects HTTP %i on newly covered team reads", async (status) => {
    const f = fake();
    f.state.inject = (path, token) => {
      if (token === TARGET && /^\/control-plane\/v1\/teams\/team-[^/]+\/sessions$/.test(path))
        return { status, body: null };
    };
    const steps = await run(f);
    expect(steps.some((s) => s.id === "team-1-private-own-sessions" && s.status === "failed")).toBe(true);
    expect(steps.length + 1).toBeLessThanOrEqual(150);
    expect(f.state.journal).toBeNull();
  });
});
