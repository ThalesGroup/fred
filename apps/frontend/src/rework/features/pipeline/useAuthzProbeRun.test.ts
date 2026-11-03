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

import { afterEach, describe, expect, it, vi } from "vitest";
import { authzProbeDeps } from "./useAuthzProbeRun";

afterEach(() => vi.unstubAllGlobals());

function mockResponses(...statuses: number[]) {
  const fetch = vi.fn(
    async (_path: RequestInfo | URL, _init?: RequestInit) => new Response(null, { status: statuses.shift() ?? 500 }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("authorization HTTP probes", () => {
  it.each(["platform_admin", "team_manager", "feature_manager"])("recognizes registry access for %s", async (role) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ permissions: { platform_roles: [role] } })),
    );
    expect((await authzProbeDeps.fetchBootstrapFlags("token")).canListAllTeams).toBe(true);
  });

  it.each(["platform_observer", "prompt_editor"])("does not grant registry access to %s", async (role) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ permissions: { platform_roles: [role] } })),
    );
    expect((await authzProbeDeps.fetchBootstrapFlags("token")).canListAllTeams).toBe(false);
  });

  it("does not treat a failed team read as absent write permission", async () => {
    mockResponses(403);
    await expect(authzProbeDeps.fetchTeamPermissions("token", "team-a")).rejects.toThrow("HTTP 403");
  });

  it("requires an id when the write endpoint reports creation", async () => {
    mockResponses(201);
    await expect(authzProbeDeps.probeTeamWriteAccess("token", "team-a")).rejects.toThrow(
      /without prompt id; check fred-authz-selftest-.* for cleanup/,
    );
  });

  it("checks that a created prompt is gone after deletion", async () => {
    const fetch = mockResponses(204, 404);
    await authzProbeDeps.cleanupTeamWrite("token", "team-a", "prompt-a");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "DELETE" });
    expect(fetch.mock.calls[1][1]).toMatchObject({ method: "GET" });
  });

  it.each([
    [500, 404, "DELETE"],
    [204, 200, "after deletion"],
  ])("reports cleanup failure for DELETE %i then GET %i", async (del, read, expected) => {
    mockResponses(del, read);
    await expect(authzProbeDeps.cleanupTeamWrite("token", "team-a", "prompt-a")).rejects.toThrow(expected);
  });
});
