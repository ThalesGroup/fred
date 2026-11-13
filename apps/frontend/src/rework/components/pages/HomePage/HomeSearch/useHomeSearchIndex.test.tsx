// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MySpace } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { INSTANCE, SPACES } from "../../TeamAgentsPage/weaverAgentFixtures";
import { promptFixture, promptSummaryFixture } from "../../PromptsPage/weaverPromptFixtures";

const h = vi.hoisted(() => ({
  context: { currentData: undefined as MySpace[] | undefined, isFetching: false, isError: false },
  refetch: vi.fn(),
  navigate: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => h.navigate }));
vi.mock("../../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy" }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showSuccess: vi.fn() }) }));
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
vi.mock("@core/hooks/useWorkingOrganization", () => ({
  useWorkingOrganization: () => ({ organizationId: "org", memberships: { ...h.context, refetch: h.refetch } }),
}));
import { enhancedControlPlaneApi as api } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useHomeSearchIndex } from "./useHomeSearchIndex";
import HomeSearch from "./HomeSearch";

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
const ALL_SPACES: MySpace[] = ["organization", "team", "project", "personal"].map((kind) => ({
  ...SPACES[0],
  id: kind,
  name: kind,
  kind: kind as MySpace["kind"],
}));
const response = (items: unknown[] = [], status = 200, next_cursor: string | null = null) =>
  new Response(JSON.stringify({ items, next_cursor }), {
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
async function render(content: ReactNode = <Probe />) {
  await act(async () => root.render(<Provider store={store}>{content}</Provider>));
  await act(async () => {
    await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
  });
}
async function search(query: string) {
  const input = host.querySelector("input")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, query);
    input.dispatchEvent(new Event("input", { bubbles: true }));
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
it("keeps its results through a memberships refresh that changes nothing", async () => {
  h.context.currentData = SPACES;
  fetch.mockImplementation(async (request) =>
    response(
      new URL(request.url).pathname.endsWith("/prompts")
        ? [promptSummaryFixture({ display_name: "Known prompt" })]
        : [],
    ),
  );
  await render();
  const calls = fetch.mock.calls.length;
  h.context.isFetching = true;
  await render();
  h.context.isFetching = false;
  await render();
  expect(host.textContent).toContain("Known prompt");
  expect(fetch).toHaveBeenCalledTimes(calls);
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

it("indexes every page in all four spaces without expanding agent calls or navigation", async () => {
  h.context.currentData = ALL_SPACES;
  fetch.mockImplementation(async (request) => {
    const url = new URL(request.url);
    const spaceId = url.pathname.split("/")[4];
    if (!url.pathname.endsWith("/prompts")) return response();
    const page = url.searchParams.has("after") ? "last" : "first";
    return response(
      [
        promptSummaryFixture({
          prompt_id: `${spaceId}-${page}`,
          space_id: spaceId,
          display_name: `${spaceId} ${page}`,
        }),
      ],
      200,
      page === "first" ? "cursor" : null,
    );
  });
  await render();
  for (const space of ALL_SPACES) expect(host.textContent).toContain(`${space.id} last`);
  expect(host.querySelector("p")!.textContent).toBe("team,personal");
  const agentPaths = fetch.mock.calls
    .map(([request]) => new URL(request.url).pathname)
    .filter((path) => !path.endsWith("/prompts"));
  expect(agentPaths).toEqual([
    "/control-plane/v1/spaces/team/agent-instances",
    "/control-plane/v1/spaces/personal/agent-instances",
  ]);
  expect(fetch).toHaveBeenCalledTimes(10);
});

it.each([403, 404])("discards cached prompt and agent results after a catalog refusal (%s)", async (status) => {
  h.context.currentData = [SPACES[0]];
  fetch.mockImplementation(async (request) =>
    response(new URL(request.url).pathname.endsWith("/prompts") ? [promptSummaryFixture()] : [INSTANCE]),
  );
  // Another mounted consumer keeps the successful RTK data alive during the failed refresh.
  const prompts = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: SPACES[0].id }));
  const agents = store.dispatch(api.endpoints.listAgentInstances.initiate({ spaceId: SPACES[0].id }));
  await Promise.all([prompts, agents]);
  fetch.mockImplementation(async () => response([], status));
  await render(<HomeSearch />);
  await search("Real");
  expect(host.querySelector('[role="option"]')).toBeNull();
  await search("Saved");
  expect(host.querySelector('[role="option"]')).toBeNull();
  expect(api.endpoints.listPrompts.select({ spaceId: SPACES[0].id })(store.getState()).data?.items).toHaveLength(1);
  prompts.unsubscribe();
  agents.unsubscribe();
});

it("does not expose a partial organization catalog after a later page is denied", async () => {
  h.context.currentData = [ALL_SPACES[0]];
  fetch.mockImplementation(async (request) =>
    new URL(request.url).searchParams.has("after")
      ? response([], 403)
      : response([promptSummaryFixture({ space_id: "organization" })], 200, "cursor"),
  );
  await render(<HomeSearch />);
  await search("Real");
  expect(host.querySelector('[role="option"]')).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("does not infer content access from an organization's technical admin role", async () => {
  h.context.currentData = [{ ...ALL_SPACES[0], roles: ["organization_admin"] }];
  fetch.mockImplementation(async () => response([], 403));
  await render(<HomeSearch />);
  await search("organization");
  expect(host.querySelector('[role="option"]')).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it.each(SPACES)("preserves agent and space navigation for $kind", async (space) => {
  h.context.currentData = [space];
  fetch.mockImplementation(async (request) =>
    response(new URL(request.url).pathname.endsWith("/agent-instances") ? [INSTANCE] : []),
  );
  await render(<HomeSearch />);
  await search("Saved Agent");
  await act(async () => host.querySelector<HTMLButtonElement>('[role="option"]')!.click());
  expect(h.navigate).toHaveBeenLastCalledWith(`/team/${space.id}/managed-chat/${INSTANCE.agent_instance_id}`);
  await search(space.name);
  await act(async () => host.querySelector<HTMLButtonElement>('[role="option"]')!.click());
  expect(h.navigate).toHaveBeenLastCalledWith(`/team/${space.id}/agents`);
});

it.each(ALL_SPACES)("opens the selected $kind prompt with its canonical space id", async (space) => {
  h.context.currentData = ALL_SPACES;
  fetch.mockImplementation(async (request) => {
    const url = new URL(request.url);
    const spaceId = url.pathname.split("/")[4];
    if (url.pathname.endsWith("/agent-instances")) return response();
    const prompt = promptFixture({
      prompt_id: `prompt-${spaceId}`,
      space_id: spaceId,
      display_name: `Prompt ${spaceId}`,
    });
    return url.pathname.endsWith("/prompts")
      ? response([prompt])
      : new Response(JSON.stringify(prompt), { headers: { "Content-Type": "application/json" } });
  });
  await render(<HomeSearch />);
  await search(`Prompt ${space.id}`);
  const option = host.querySelector<HTMLButtonElement>('[role="option"]');
  expect(option?.textContent).toContain(`Prompt ${space.id}`);
  await act(async () => option!.click());
  await act(async () => {
    await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
  });
  expect(fetch.mock.calls.map(([request]) => new URL(request.url).pathname)).toContain(
    `/control-plane/v1/spaces/${space.id}/prompts/prompt-${space.id}`,
  );
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("Real prompt text");
  expect(h.navigate).not.toHaveBeenCalled();
});

it("removes a prompt preview when its detail is refused after access is revoked", async () => {
  h.context.currentData = [ALL_SPACES[0]];
  let revoked = false;
  fetch.mockImplementation(async (request) => {
    if (!new URL(request.url).pathname.endsWith("/prompts")) {
      revoked = true;
      return response([], 403);
    }
    return revoked ? response([], 403) : response([promptSummaryFixture({ space_id: "organization" })]);
  });
  await render(<HomeSearch />);
  await search("Real Name");
  await act(async () => host.querySelector<HTMLButtonElement>('[role="option"]')!.click());
  await act(async () => {
    await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
  });
  await act(async () => {
    await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
  });
  await search("Real");
  expect(host.querySelector('[role="option"]')).toBeNull();
  expect(document.body.textContent).not.toContain("Real prompt text");
  expect(fetch).toHaveBeenCalledTimes(3);
});
