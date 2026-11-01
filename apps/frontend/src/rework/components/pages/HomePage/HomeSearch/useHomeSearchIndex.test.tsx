// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MySpace } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { SPACES } from "../../TeamAgentsPage/weaverAgentFixtures";
import { promptSummaryFixture } from "../../PromptsPage/weaverPromptFixtures";

const h = vi.hoisted(() => ({
  context: { currentData: undefined as MySpace[] | undefined, isFetching: false, isError: false },
  refetch: vi.fn(),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useMySpacesQuery: () => ({ ...h.context, refetch: h.refetch }),
}));
vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "fixture",
    GetUserId: () => "user",
    GetSessionIdentity: () => "fixture/user",
    ensureFreshToken: async () => true,
  },
}));
vi.mock("../../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
import { enhancedControlPlaneApi as api } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useHomeSearchIndex } from "./useHomeSearchIndex";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const NativeRequest = globalThis.Request;
let host: HTMLDivElement;
let root: Root;
let renders: number;
let store: ReturnType<typeof makeStore>;
const makeStore = () =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) => defaults().concat(api.middleware),
  });
const fetch = vi.fn<(request: Request) => Promise<Response>>();
const response = (items: unknown[] = [], status = 200) =>
  new Response(JSON.stringify({ items, next_cursor: null }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function Probe() {
  const sources = useHomeSearchIndex(true);
  const [clicks, setClicks] = useState(0);
  if (++renders > 30) throw new Error("Home search did not settle");
  return (
    <>
      <p>{sources.teams.map((team) => team.name).join(",")}</p>
      <p>{sources.prompts.map((prompt) => prompt.name).join(",")}</p>
      <p>{sources.isError ? "failed" : "ready"}</p>
      <button onClick={() => setClicks((value) => value + 1)}>clicks {clicks}</button>
    </>
  );
}
async function render() {
  await act(async () =>
    root.render(
      <Provider store={store}>
        <Probe />
      </Provider>,
    ),
  );
  await act(async () => {
    await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  h.context = { currentData: undefined, isFetching: false, isError: false };
  renders = 0;
  fetch.mockImplementation(async () => response());
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  store.dispatch(api.util.resetApiState());
  host.remove();
  vi.unstubAllGlobals();
});
it.each([true, false])("settles and remains interactive without space data (loading=%s)", async (isFetching) => {
  h.context.isFetching = isFetching;
  await render();
  expect(renders).toBeLessThan(10);
  expect(fetch).not.toHaveBeenCalled();
  await act(async () => host.querySelector("button")!.click());
  expect(host.textContent).toContain("clicks 1");
});
it("loads personal and shared catalogs through Weaver and discards data after a scope change", async () => {
  h.context.currentData = SPACES;
  fetch.mockImplementation(async (request) =>
    response(
      new URL(request.url).pathname.endsWith("/prompts")
        ? [promptSummaryFixture({ display_name: "Known prompt" })]
        : [],
    ),
  );
  await render();
  expect(host.textContent, JSON.stringify(fetch.mock.calls.map(([request]) => request.url))).toContain("Known prompt");
  expect(fetch).toHaveBeenCalledTimes(4);
  expect(
    fetch.mock.calls.every(([request]) => new URL(request.url).pathname.startsWith("/control-plane/v1/spaces/")),
  ).toBe(true);
  h.context.currentData = [];
  await render();
  expect(host.textContent).not.toContain("Known prompt");
});
it("surfaces an unavailable catalog without a render or request loop", async () => {
  h.context.currentData = [SPACES[0]];
  fetch.mockImplementation(async () => response([], 503));
  await render();
  expect(host.textContent).toContain("failed");
  const calls = fetch.mock.calls.length;
  await act(async () => host.querySelector("button")!.click());
  expect(fetch).toHaveBeenCalledTimes(calls);
});
