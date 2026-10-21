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
import type { AuthzProbeDeps } from "./authzProbeScenario";
import {
  ADMIN_ROUTES,
  authorizationScenario,
  MAX_FOREIGN_TEAMS,
  MEMBER_ROUTES,
  protectedRoutes,
  resign,
  type AuthorizationDeps,
} from "./authorizationScenario";
import { collect, signal } from "./fakePlatform";

const TOKEN = "aGVhZGVy.cGF5bG9hZA.c2lnbmF0dXJl";

const probe: AuthzProbeDeps = {
  fetchBootstrapFlags: async () => ({ isPlatformAdmin: true, isPlatformObserver: false, canListAllTeams: true }),
  fetchOwnTeamIds: async () => ["mine"],
  probeRegistryAccess: async () => ({
    status: 200,
    teamIds: ["mine", "personal-x", ...Array.from({ length: 7 }, (_, i) => `t${i}`)],
  }),
  probeUsersAccess: async () => 200,
  probeTeamPromptsAccess: async () => 403,
  fetchTeamPermissions: async () => ["can_update_resources"],
  probeTeamWriteAccess: async () => ({ status: 201, createdId: "p" }),
  cleanupTeamWrite: async () => {},
};

/** A correct deployment: 401 without a valid token, admin routes open, foreign team content refused. */
function secure(path: string, token?: string): number {
  if (token !== TOKEN) return 401;
  if (/\/teams\/t\d\//.test(path)) return 403;
  return 200;
}

function deps(answer: (path: string, token?: string) => number = secure, calls: string[] = []): AuthorizationDeps {
  return {
    probe,
    request: async (path, token) => {
      calls.push(path);
      return { status: answer(path, token), body: null };
    },
    token: async () => TOKEN,
    personalTeamId: "personal-admin",
  };
}

async function run(d: AuthorizationDeps) {
  const r = collect();
  await authorizationScenario(d, r.report, signal);
  return r;
}

describe("authorizationScenario", () => {
  it("passes every sweep on a deployment that refuses what it should", async () => {
    const r = await run(deps());
    for (const id of ["sweep-missing", "sweep-malformed", "sweep-resigned", "admin-routes", "foreign-team-sweep"]) {
      expect(r.status(id), id).toBe("passed");
    }
    expect(r.status("foreign-team-isolation")).toBe("passed");
  });

  it("names a route that answers without a token", async () => {
    const leaky = (path: string, token?: string) => (path.endsWith("/marketplace/agents") ? 200 : secure(path, token));
    const r = await run(deps(leaky));
    expect(r.status("sweep-missing")).toBe("failed");
    expect(r.steps.find((s) => s.id === "sweep-missing")?.error).toContain("/marketplace/agents: HTTP 200");
  });

  it.each([
    ["missing", undefined],
    ["malformed", "not-a-jwt"],
    ["resigned", resign(TOKEN)],
  ])("finds a leaked route in the %s token sweep", async (mode, credential) => {
    const d = deps((path, token) => (path.endsWith("/tags") && token === credential ? 200 : secure(path, token)));
    const r = await run(d);
    expect(r.status(`sweep-${mode}`)).toBe("failed");
    expect(r.steps.find((s) => s.id === `sweep-${mode}`)?.error).toContain("/knowledge-flow/v1/tags: HTTP 200");
  });

  it("fails when a public team's members are listed to a non-member", async () => {
    const leaky = (path: string, token?: string) => (path.endsWith("/t2/members") ? 200 : secure(path, token));
    const r = await run(deps(leaky));
    expect(r.status("foreign-team-sweep")).toBe("failed");
  });

  it.each([200, 401, 500])("rejects HTTP %i on foreign team content", async (status) => {
    const d = deps((path, token) => (path.endsWith("/t2/members") && token === TOKEN ? status : secure(path, token)));
    const r = await run(d);
    expect(r.status("foreign-team-sweep")).toBe("failed");
    expect(r.steps.find((s) => s.id === "foreign-team-sweep")?.error).toContain(`t2/members: HTTP ${status}`);
  });

  it("skips foreign content checks when the registry cannot be read", async () => {
    const d = deps();
    d.probe = { ...probe, probeRegistryAccess: async () => ({ status: 403, teamIds: [] }) };
    expect((await run(d)).status("foreign-team-sweep")).toBe("skipped");
  });

  it("bounds the foreign sweep and never probes the personal space", async () => {
    const calls: string[] = [];
    await run(deps(secure, calls));
    const foreign = calls.filter((p) => /\/teams\/t\d\//.test(p));
    expect(foreign).toHaveLength(MAX_FOREIGN_TEAMS * MEMBER_ROUTES.length);
    expect(calls.some((p) => p.includes("/teams/personal-x/"))).toBe(false);
  });

  it("fails an admin route closed to the platform admin", async () => {
    const closed = (path: string, token?: string) => (path === ADMIN_ROUTES[2] && token ? 403 : secure(path, token));
    expect((await run(deps(closed))).status("admin-routes")).toBe("failed");
  });

  it.each([401, 500, 502])("fails an admin route returning HTTP %i for a non-admin", async (status) => {
    const d = deps((path, token) => {
      if (token !== TOKEN) return 401;
      if (path === ADMIN_ROUTES[2]) return status;
      if (ADMIN_ROUTES.includes(path)) return 403;
      return secure(path, token);
    });
    d.probe = {
      ...probe,
      fetchBootstrapFlags: async () => ({ isPlatformAdmin: false, isPlatformObserver: false, canListAllTeams: false }),
    };
    const r = await run(d);
    expect(r.status("admin-routes")).toBe("failed");
    expect(r.steps.find((s) => s.id === "admin-routes")?.error).toContain(`HTTP ${status}`);
  });

  it("continues all three token sweeps after one route leaks", async () => {
    const leaky = (path: string, token?: string) =>
      path === ADMIN_ROUTES[2] && token === undefined ? 200 : secure(path, token);
    const calls: string[] = [];
    const r = await run(deps(leaky, calls));
    expect(r.status("sweep-missing")).toBe("failed");
    expect(r.status("sweep-malformed")).toBe("passed");
    expect(r.status("sweep-resigned")).toBe("passed");
    expect(calls).toContain("/fred/agents/v2/agents/sessions");
  });

  it("skips the forged-signature sweep for an unsigned credential, and stops without a session", async () => {
    expect(resign("opaque")).toBeNull();
    expect(resign(TOKEN)).not.toBe(TOKEN);
    const d = deps();
    d.token = async () => null;
    const r = await run(d);
    expect(r.status("session-token")).toBe("failed");
    expect(r.steps).toHaveLength(1);
    expect(protectedRoutes("personal-a").filter((p) => p.includes("personal-a"))).toHaveLength(3);
  });
});
