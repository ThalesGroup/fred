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
