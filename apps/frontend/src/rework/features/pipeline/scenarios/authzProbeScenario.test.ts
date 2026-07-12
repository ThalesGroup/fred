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
import {
  assertAccessMatchesPlatformAdmin,
  assertWriteAccessMatchesTeamPermission,
  authzProbeScenario,
  type AuthzProbeDeps,
  type BootstrapFlags,
  type RegistryProbeResult,
  type TeamWriteProbeResult,
} from "./authzProbeScenario";
import type { StepReport } from "../types";

describe("assertAccessMatchesPlatformAdmin", () => {
  it("does not throw when a platform_admin is allowed (200)", () => {
    expect(() => assertAccessMatchesPlatformAdmin("x", 200, true)).not.toThrow();
  });
  it("does not throw when a non-admin is denied (403)", () => {
    expect(() => assertAccessMatchesPlatformAdmin("x", 403, false)).not.toThrow();
  });
  it("throws when a non-admin is unexpectedly allowed (200)", () => {
    expect(() => assertAccessMatchesPlatformAdmin("registry access", 200, false)).toThrow(/is_platform_admin=false/);
  });
  it("throws when a platform_admin is unexpectedly denied (403)", () => {
    expect(() => assertAccessMatchesPlatformAdmin("registry access", 403, true)).toThrow(/is_platform_admin=true/);
  });
});

describe("assertWriteAccessMatchesTeamPermission", () => {
  it("does not throw when a permitted write succeeds (201)", () => {
    expect(() => assertWriteAccessMatchesTeamPermission("x", 201, true)).not.toThrow();
  });
  it("does not throw when a write without the permission is denied (403)", () => {
    expect(() => assertWriteAccessMatchesTeamPermission("x", 403, false)).not.toThrow();
  });
  it("throws when a write without the permission unexpectedly succeeds (200)", () => {
    expect(() => assertWriteAccessMatchesTeamPermission("team x write access", 200, false)).toThrow(
      /can_update_resources=false/,
    );
  });
  it("throws when a permitted write is unexpectedly denied (403)", () => {
    expect(() => assertWriteAccessMatchesTeamPermission("team x write access", 403, true)).toThrow(
      /can_update_resources=true/,
    );
  });
});

/** Build a fake AuthzProbeDeps from a fixed script, ignoring which token was passed
 * (the scenario's own logic of *which* token to use for *which* call is what's under test). */
function fakeDeps(script: {
  flags: BootstrapFlags;
  ownTeamIds: string[];
  registryByToken: (token: string) => RegistryProbeResult;
  usersStatus: number;
  promptsStatusByTeam: Record<string, number>;
  teamPermissionsByTeam?: Record<string, string[]>;
  writeProbeByTeam?: Record<string, TeamWriteProbeResult>;
}): AuthzProbeDeps & { cleanupCalls: Array<{ teamId: string; promptId: string }> } {
  const cleanupCalls: Array<{ teamId: string; promptId: string }> = [];
  return {
    fetchBootstrapFlags: async () => script.flags,
    fetchOwnTeamIds: async () => script.ownTeamIds,
    probeRegistryAccess: async (token) => script.registryByToken(token),
    probeUsersAccess: async () => script.usersStatus,
    probeTeamPromptsAccess: async (_token, teamId) => script.promptsStatusByTeam[teamId] ?? 404,
    fetchTeamPermissions: async (_token, teamId) => script.teamPermissionsByTeam?.[teamId] ?? [],
    probeTeamWriteAccess: async (_token, teamId) =>
      script.writeProbeByTeam?.[teamId] ?? { status: 403, createdId: null },
    cleanupTeamWrite: async (_token, teamId, promptId) => {
      cleanupCalls.push({ teamId, promptId });
    },
    cleanupCalls,
  };
}

async function runScenario(adminToken: string, targetToken: string, deps: AuthzProbeDeps): Promise<StepReport[]> {
  const steps: StepReport[] = [];
  await authzProbeScenario(adminToken, targetToken, deps, (step) => {
    const i = steps.findIndex((s) => s.id === step.id);
    if (i === -1) steps.push(step);
    else steps[i] = step;
  });
  return steps;
}

function statusOf(steps: StepReport[], id: string): string {
  return steps.find((s) => s.id === id)?.status ?? "missing";
}

describe("authzProbeScenario", () => {
  it("passes every step for the running admin testing themselves", async () => {
    const deps = fakeDeps({
      flags: { isPlatformAdmin: true, isPlatformObserver: true },
      ownTeamIds: [],
      registryByToken: () => ({ status: 200, teamIds: ["team-a", "team-b"] }),
      usersStatus: 200,
      promptsStatusByTeam: { "team-a": 403, "team-b": 403 },
    });
    const steps = await runScenario("admin-token", "admin-token", deps);
    for (const id of ["bootstrap-flags", "own-teams", "registry-access", "users-access", "foreign-team-isolation"]) {
      expect(statusOf(steps, id), id).toBe("passed");
    }
    // No collaborative team of their own to probe a write against.
    expect(statusOf(steps, "team-write-access")).toBe("skipped");
  });

  it("passes every step for a correctly-denied non-admin profile", async () => {
    const deps = fakeDeps({
      flags: { isPlatformAdmin: false, isPlatformObserver: false },
      ownTeamIds: ["team-a"],
      registryByToken: (token) =>
        token === "admin-token" ? { status: 200, teamIds: ["team-a", "team-b"] } : { status: 403, teamIds: [] },
      usersStatus: 403,
      promptsStatusByTeam: { "team-b": 403 },
      // Unscripted for "team-a": defaults to no permission + denied write — consistent.
    });
    const steps = await runScenario("admin-token", "bob-token", deps);
    for (const id of [
      "bootstrap-flags",
      "own-teams",
      "team-write-access",
      "registry-access",
      "users-access",
      "foreign-team-isolation",
    ]) {
      expect(statusOf(steps, id), id).toBe("passed");
    }
    expect(steps.find((s) => s.id === "foreign-team-isolation")?.detail).toContain("team-b");
  });

  it("fails registry-access when a non-admin is unexpectedly let in", async () => {
    const deps = fakeDeps({
      flags: { isPlatformAdmin: false, isPlatformObserver: false },
      ownTeamIds: [],
      registryByToken: () => ({ status: 200, teamIds: ["team-a"] }), // bug: 200 for a non-admin
      usersStatus: 403,
      promptsStatusByTeam: {},
    });
    const steps = await runScenario("admin-token", "eve-token", deps);
    expect(statusOf(steps, "registry-access")).toBe("failed");
  });

  it("fails foreign-team-isolation when a foreign team is unexpectedly readable", async () => {
    const deps = fakeDeps({
      flags: { isPlatformAdmin: true, isPlatformObserver: true },
      ownTeamIds: [],
      registryByToken: () => ({ status: 200, teamIds: ["team-a"] }),
      usersStatus: 200,
      promptsStatusByTeam: { "team-a": 200 }, // bug: admin can read a team it holds no relation to
    });
    const steps = await runScenario("admin-token", "admin-token", deps);
    expect(statusOf(steps, "foreign-team-isolation")).toBe("failed");
  });

  it("skips foreign-team-isolation when the target already belongs to every team", async () => {
    const deps = fakeDeps({
      flags: { isPlatformAdmin: false, isPlatformObserver: false },
      ownTeamIds: ["team-a"],
      registryByToken: (token) =>
        token === "admin-token" ? { status: 200, teamIds: ["team-a"] } : { status: 403, teamIds: [] },
      usersStatus: 403,
      promptsStatusByTeam: {},
    });
    const steps = await runScenario("admin-token", "full-member-token", deps);
    expect(statusOf(steps, "foreign-team-isolation")).toBe("skipped");
  });

  describe("team-write-access", () => {
    it("passes for a team_editor-equivalent account that can write", async () => {
      const deps = fakeDeps({
        flags: { isPlatformAdmin: false, isPlatformObserver: false },
        ownTeamIds: ["team-a"],
        registryByToken: () => ({ status: 403, teamIds: [] }),
        usersStatus: 403,
        promptsStatusByTeam: {},
        teamPermissionsByTeam: { "team-a": ["can_update_resources"] },
        writeProbeByTeam: { "team-a": { status: 201, createdId: "prompt-123" } },
      });
      const steps = await runScenario("admin-token", "sophia-token", deps);
      expect(statusOf(steps, "team-write-access")).toBe("passed");
      expect(steps.find((s) => s.id === "team-write-access")?.detail).toContain("can_update_resources=true");
    });

    it("cleans up the created prompt after a successful write", async () => {
      const deps = fakeDeps({
        flags: { isPlatformAdmin: false, isPlatformObserver: false },
        ownTeamIds: ["team-a"],
        registryByToken: () => ({ status: 403, teamIds: [] }),
        usersStatus: 403,
        promptsStatusByTeam: {},
        teamPermissionsByTeam: { "team-a": ["can_update_resources"] },
        writeProbeByTeam: { "team-a": { status: 201, createdId: "prompt-123" } },
      });
      await runScenario("admin-token", "sophia-token", deps);
      expect(deps.cleanupCalls).toEqual([{ teamId: "team-a", promptId: "prompt-123" }]);
    });

    it("does not attempt cleanup when the write was correctly denied", async () => {
      const deps = fakeDeps({
        flags: { isPlatformAdmin: false, isPlatformObserver: false },
        ownTeamIds: ["team-a"],
        registryByToken: () => ({ status: 403, teamIds: [] }),
        usersStatus: 403,
        promptsStatusByTeam: {},
        teamPermissionsByTeam: { "team-a": [] },
        writeProbeByTeam: { "team-a": { status: 403, createdId: null } },
      });
      await runScenario("admin-token", "phil-token", deps);
      expect(deps.cleanupCalls).toEqual([]);
    });

    it("fails when a write succeeds despite the account lacking can_update_resources", async () => {
      const deps = fakeDeps({
        flags: { isPlatformAdmin: false, isPlatformObserver: false },
        ownTeamIds: ["team-a"],
        registryByToken: () => ({ status: 403, teamIds: [] }),
        usersStatus: 403,
        promptsStatusByTeam: {},
        teamPermissionsByTeam: { "team-a": [] }, // plain team_member — no write permission
        writeProbeByTeam: { "team-a": { status: 201, createdId: "prompt-999" } }, // bug: write succeeded anyway
      });
      const steps = await runScenario("admin-token", "phil-token", deps);
      expect(statusOf(steps, "team-write-access")).toBe("failed");
      // Still cleans up the prompt it created, bug or not.
      expect(deps.cleanupCalls).toEqual([{ teamId: "team-a", promptId: "prompt-999" }]);
    });

    it("fails when a write is denied despite the account holding can_update_resources", async () => {
      const deps = fakeDeps({
        flags: { isPlatformAdmin: false, isPlatformObserver: false },
        ownTeamIds: ["team-a"],
        registryByToken: () => ({ status: 403, teamIds: [] }),
        usersStatus: 403,
        promptsStatusByTeam: {},
        teamPermissionsByTeam: { "team-a": ["can_update_resources"] },
        writeProbeByTeam: { "team-a": { status: 403, createdId: null } }, // bug: denied despite the permission
      });
      const steps = await runScenario("admin-token", "sophia-token", deps);
      expect(statusOf(steps, "team-write-access")).toBe("failed");
    });

    it("skips when the target belongs to no collaborative team", async () => {
      const deps = fakeDeps({
        flags: { isPlatformAdmin: false, isPlatformObserver: false },
        ownTeamIds: [],
        registryByToken: () => ({ status: 403, teamIds: [] }),
        usersStatus: 403,
        promptsStatusByTeam: {},
      });
      const steps = await runScenario("admin-token", "gabriel-token", deps);
      expect(statusOf(steps, "team-write-access")).toBe("skipped");
    });
  });
});
