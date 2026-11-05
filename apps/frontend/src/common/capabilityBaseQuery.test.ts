// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, expect, it, vi } from "vitest";
import { capabilityRoutingSlice, setCapabilityBaseUrls } from "./capabilityRoutingSlice";
import { pptBuilderCapabilityApi } from "../rework/features/capabilities/ppt_builder/api/pptBuilderCapabilityOpenApi";

vi.mock("../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "person",
    ensureFreshToken: async () => true,
    CallLogout: vi.fn(),
  },
}));
vi.mock("./platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
afterEach(() => vi.unstubAllGlobals());

it("routes concurrent offers explicitly and caches builtin inventories by organization and pod", async () => {
  const requests: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push(request.url);
      expect(request.headers.get("Authorization")).toBe("Bearer person");
      const url = new URL(request.url);
      return new Response(
        JSON.stringify({ inventory: { patterns: [], marker: url.hostname + url.searchParams.get("space_id") } }),
        { headers: { "Content-Type": "application/json" } },
      );
    }),
  );
  const store = configureStore({
    reducer: {
      capabilityRouting: capabilityRoutingSlice.reducer,
      [pptBuilderCapabilityApi.reducerPath]: pptBuilderCapabilityApi.reducer,
    },
    middleware: (get) => get().concat(pptBuilderCapabilityApi.middleware),
  });
  store.dispatch(
    setCapabilityBaseUrls({
      ppt_builder: "https://wrong.invalid/ppt_builder",
      "org-a/pod-a/ppt_builder": "https://pod-a.invalid/ppt_builder",
      "org-a/pod-b/ppt_builder": "https://pod-b.invalid/ppt_builder",
      "org-b/pod-a/ppt_builder": "https://pod-a.invalid/ppt_builder",
    }),
  );
  const scopes = [
    { spaceId: "org-a", runtimeId: "pod-a" },
    { spaceId: "org-a", runtimeId: "pod-b" },
    { spaceId: "org-b", runtimeId: "pod-a" },
  ];
  const queries = scopes.map((scope) =>
    store.dispatch(pptBuilderCapabilityApi.endpoints.getPptBuilderBuiltin.initiate(scope)),
  );
  const results = await Promise.all(queries.map((query) => query.unwrap()));
  expect(new Set(results.map((result) => JSON.stringify(result))).size).toBe(3);
  expect(requests).toHaveLength(3);
  expect(requests.some((url) => url.includes("wrong.invalid"))).toBe(false);
  scopes.forEach((scope, i) =>
    expect(pptBuilderCapabilityApi.endpoints.getPptBuilderBuiltin.select(scope)(store.getState()).data).toEqual(
      results[i],
    ),
  );
  queries.forEach((query) => query.unsubscribe());
  store.dispatch(pptBuilderCapabilityApi.util.resetApiState());
});
