// @vitest-environment happy-dom
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

// The home cleanup tool deletes conversations across several spaces at once,
// while the team sidebar's list is cached per space. These drive the real
// store so a tag that no longer matches between the two fails here — asserting
// the tag objects alone would still pass with a mismatched id string.

import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enhancedControlPlaneApi as api } from "./controlPlaneApiEnhancements";

vi.mock("../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "test-token",
    ensureFreshToken: async () => true,
    CallLogout: () => {},
  },
}));

const teamSessionsPath = (teamId: string) => `/control-plane/v1/teams/${teamId}/sessions`;
const inactivePath = "/control-plane/v1/me/inactive-sessions";

let requested: string[] = [];

const callsTo = (path: string) => requested.filter((url) => new URL(url).pathname === path).length;

const makeStore = () =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
  });

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  requested = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | string) => {
      const url = typeof input === "string" ? input : input.url;
      requested.push(url);
      const { pathname } = new URL(url);
      if (pathname === inactivePath) return json({ sessions: [] });
      if (pathname.endsWith("/bulk-delete")) return json({ deleted: ["s1", "s2"], failed: [] });
      return json([]);
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("bulk session delete invalidation", () => {
  it("refetches the conversation list of every space it deleted from, and only those", async () => {
    const store = makeStore();
    const teamA = store.dispatch(
      api.endpoints.getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet.initiate({ teamId: "team-a" }),
    );
    const teamB = store.dispatch(
      api.endpoints.getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet.initiate({ teamId: "team-b" }),
    );
    await Promise.all([teamA, teamB]);
    expect(callsTo(teamSessionsPath("team-a"))).toBe(1);
    expect(callsTo(teamSessionsPath("team-b"))).toBe(1);

    await store.dispatch(
      api.endpoints.postBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePost.initiate({
        bulkDeleteSessionsRequest: {
          sessions: [
            { session_id: "s1", team_id: "team-a" },
            { session_id: "s2", team_id: "team-a" },
          ],
        },
      }),
    );

    // Without the per-space invalidation the list keeps its cached rows, and a
    // user clicking one lands on an empty conversation.
    await vi.waitFor(() => expect(callsTo(teamSessionsPath("team-a"))).toBe(2));
    expect(callsTo(teamSessionsPath("team-b"))).toBe(1);

    teamA.unsubscribe();
    teamB.unsubscribe();
  });

  it("still refreshes the home page's inactive-conversations list", async () => {
    const store = makeStore();
    const inactive = store.dispatch(
      api.endpoints.getMyInactiveSessionsControlPlaneV1MeInactiveSessionsGet.initiate({}),
    );
    await inactive;
    expect(callsTo(inactivePath)).toBe(1);

    await store.dispatch(
      api.endpoints.postBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePost.initiate({
        bulkDeleteSessionsRequest: { sessions: [{ session_id: "s1", team_id: "team-a" }] },
      }),
    );

    await vi.waitFor(() => expect(callsTo(inactivePath)).toBe(2));
    inactive.unsubscribe();
  });
});

describe("capability enablement invalidation", () => {
  const agentsPath = (teamId: string) => `/control-plane/v1/teams/${teamId}/agent-instances`;

  const loadAgentLists = async (store: ReturnType<typeof makeStore>) => {
    const subs = ["team-a", "team-b"].map((teamId) =>
      store.dispatch(
        api.endpoints.getTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGet.initiate({ teamId }),
      ),
    );
    await Promise.all(subs);
    return () => subs.forEach((sub) => sub.unsubscribe());
  };

  // A disable suspends the team's agents server-side; without this the list
  // keeps showing them active until a page reload.
  it("refetches the agent list of the team whose capability changed, and only that one", async () => {
    const store = makeStore();
    const release = await loadAgentLists(store);

    await store.dispatch(
      api.endpoints.deleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDelete.initiate({
        capabilityId: "html_artifact",
        teamId: "team-a",
        mode: "disable",
      }),
    );

    await vi.waitFor(() => expect(callsTo(agentsPath("team-a"))).toBe(2));
    expect(callsTo(agentsPath("team-b"))).toBe(1);
    release();
  });

  it("refetches every agent list after a platform-wide switch", async () => {
    const store = makeStore();
    const release = await loadAgentLists(store);

    await store.dispatch(
      api.endpoints.putCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPut.initiate({
        capabilityId: "html_artifact",
        setCapabilityDefaultOnRequest: { default_on: false },
      }),
    );

    await vi.waitFor(() => expect(callsTo(agentsPath("team-a"))).toBe(2));
    await vi.waitFor(() => expect(callsTo(agentsPath("team-b"))).toBe(2));
    release();
  });
});

describe("team creation admission invalidation", () => {
  it("makes a newly created team available for Free enrollment without reloading", async () => {
    const store = makeStore();
    const teamsPath = "/control-plane/v1/teams/all";
    const admissionPath = "/control-plane/v1/admin/platform/access/teams";
    let created = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        requested.push(request.url);
        const { pathname } = new URL(request.url);
        if (pathname === "/control-plane/v1/teams" && request.method === "POST") {
          created = true;
          return json({ id: "new-team", name: "New team" });
        }
        if (pathname === teamsPath) return json(created ? [{ id: "new-team", name: "New team" }] : []);
        if (pathname === admissionPath)
          return json(created ? [{ team_id: "new-team", name: "New team", allowed: false, free: false }] : []);
        return json([]);
      }),
    );
    const teams = store.dispatch(
      api.endpoints.listAllTeamsControlPlaneV1TeamsAllGet.initiate({ includeMembership: true }),
    );
    const admission = store.dispatch(
      api.endpoints.listPlatformAccessTeamsControlPlaneV1AdminPlatformAccessTeamsGet.initiate(),
    );
    try {
      await Promise.all([teams, admission]);
      await store
        .dispatch(
          api.endpoints.createTeamControlPlaneV1TeamsPost.initiate({
            createTeamRequest: { name: "New team", initial_team_admin_ids: ["admin"] },
          }),
        )
        .unwrap();
      await vi.waitFor(() => {
        expect(callsTo(teamsPath)).toBe(2);
        expect(callsTo(admissionPath)).toBe(2);
        expect(
          api.endpoints.listPlatformAccessTeamsControlPlaneV1AdminPlatformAccessTeamsGet.select()(store.getState())
            .data,
        ).toEqual([{ team_id: "new-team", name: "New team", allowed: false, free: false }]);
      });
    } finally {
      teams.unsubscribe();
      admission.unsubscribe();
      store.dispatch(api.util.resetApiState());
    }
  });
});

describe("team models save", () => {
  const policyPath = "/control-plane/v1/teams/team-a/routing-policy";
  const agentsPath = "/control-plane/v1/teams/team-a/agent-instances";

  it("writes the saved policy into the cache and refetches the team's agent list", async () => {
    let policyReads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: Request | string) => {
        const request = typeof input === "string" ? new Request(input) : input;
        requested.push(request.url);
        const { pathname } = new URL(request.url);
        if (pathname === policyPath && request.method === "PATCH") {
          return json({ team_id: "team-a", version: 2, disabled_model_ids: ["model__b"] });
        }
        if (pathname === policyPath) {
          policyReads += 1;
          // The refetch never answers: only the PATCH response can update the cache.
          if (policyReads > 1) return new Promise<Response>(() => {});
          return json({ team_id: "team-a", version: 1, disabled_model_ids: [] });
        }
        return json([]);
      }),
    );
    const store = makeStore();
    const policy = store.dispatch(
      api.endpoints.getTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGet.initiate({ teamId: "team-a" }),
    );
    const agents = store.dispatch(
      api.endpoints.getTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGet.initiate({ teamId: "team-a" }),
    );
    await Promise.all([policy, agents]);

    await store.dispatch(
      api.endpoints.updateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatch.initiate({
        teamId: "team-a",
        updateTeamRoutingPolicyRequest: { disabled_model_ids: ["model__b"], expected_version: 1 },
      }),
    );

    await vi.waitFor(() =>
      expect(
        api.endpoints.getTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGet.select({ teamId: "team-a" })(
          store.getState(),
        ).data?.version,
      ).toBe(2),
    );
    await vi.waitFor(() => expect(callsTo(agentsPath)).toBe(2));
    policy.unsubscribe();
    agents.unsubscribe();
  });
});
