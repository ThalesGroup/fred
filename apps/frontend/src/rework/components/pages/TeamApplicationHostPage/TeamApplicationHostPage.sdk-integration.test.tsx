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

import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

interface PackedClient {
  readonly context: unknown;
  connect(): Promise<{
    route: { subPath: string };
    team: { id: string };
  }>;
  onRoute(listener: (route: { subPath: string }) => void): () => void;
  navigate(path: string, options?: { replace?: boolean }): void;
  openChat(sessionId?: string | null): void;
  request(path: string, init?: { method?: string; body?: string; timeoutMs?: number }): Promise<Response>;
  dispose(): void;
}

interface PackedSdkModule {
  createFredApplicationClient(options: {
    hostOrigin: string;
    applicationId: string;
    connectionTimeoutMs?: number;
    requestTimeoutMs?: number;
  }): PackedClient;
}

const h = vi.hoisted(() => ({
  appId: "example",
  navigate: vi.fn(),
  request: vi.fn(),
  subPath: "",
  teamId: "team-1",
  teamName: "Team One",
  agents: [] as Array<{ agent_instance_id: string; status?: string }>,
  result: {
    data: {
      items: [
        {
          id: "example",
          version: "1.0.0",
          name: { en: "Example App" },
          description: { en: "An example" },
          icon: "extension",
          ui_prefix: "/apps/example-ui/",
        },
      ],
    },
    isLoading: false,
    isError: false,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en" },
  }),
}));
vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: h.teamId, appId: h.appId, "*": h.subPath }),
  useNavigate: () => h.navigate,
}));
vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({
    teamId: h.teamId,
    isPersonalTeam: false,
    selectedTeam: { id: h.teamId, name: h.teamName },
  }),
}));
vi.mock("@rework/features/applications/useTeamApplications.ts", () => ({
  useTeamApplications: () => h.result,
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi.ts", () => ({
  useLazyGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery: () => [
    () => ({ unwrap: () => Promise.resolve([]) }),
  ],
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: () => [
    () => ({ unwrap: () => Promise.resolve(h.agents) }),
  ],
}));
vi.mock("@rework/features/applications/applicationRequest.ts", () => ({
  createApplicationRequest: () => h.request,
}));

import TeamApplicationHostPage from "./TeamApplicationHostPage.tsx";

const FRED_ORIGIN = "http://localhost:3000";
const sdkEntry = process.env.FRED_IFRAME_SDK_ENTRY_URL;
const integration = sdkEntry ? describe : describe.skip;

let sdk: PackedSdkModule;
let container: HTMLDivElement | undefined;
let root: Root | undefined;
let client: PackedClient | undefined;

beforeAll(async () => {
  if (!sdkEntry) return;
  sdk = (await import(/* @vite-ignore */ sdkEntry)) as PackedSdkModule;
  const settings = (globalThis as unknown as { happyDOM?: { settings?: { fetch?: Record<string, unknown> } } }).happyDOM
    ?.settings;
  if (settings?.fetch) {
    settings.fetch.interceptor = {
      beforeAsyncRequest: async () =>
        new Response("<!doctype html><title>app</title>", { headers: { "content-type": "text/html" } }),
    };
  }
});

async function rerender() {
  await act(async () => {
    root?.render(
      <StrictMode>
        <TeamApplicationHostPage />
      </StrictMode>,
    );
    await Promise.resolve();
  });
}

async function renderPage() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await rerender();
}

function frameWindow(): Window {
  const child = container?.querySelector("iframe")?.contentWindow;
  if (!child) throw new Error("integration setup: hosted iframe has no content window");
  return child;
}

function createPackedClient(child: Window): PackedClient {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  if (!descriptor) throw new Error("integration setup: global window descriptor is unavailable");
  Object.defineProperty(globalThis, "window", { ...descriptor, value: child });
  try {
    return sdk.createFredApplicationClient({
      hostOrigin: FRED_ORIGIN,
      applicationId: "example",
      connectionTimeoutMs: 1_000,
      requestTimeoutMs: 1_000,
    });
  } finally {
    Object.defineProperty(globalThis, "window", descriptor);
  }
}

async function connectPackedSdk(options: { duplicateResponses?: boolean } = {}) {
  await renderPage();
  const host = window;
  const child = frameWindow();
  Object.defineProperty(child, "parent", {
    configurable: true,
    value: host,
  });
  expect(child.parent).toBe(host);

  vi.spyOn(host, "postMessage").mockImplementation((message, targetOrigin) => {
    expect(targetOrigin).toBe(FRED_ORIGIN);
    host.dispatchEvent(new MessageEvent("message", { data: message, origin: FRED_ORIGIN, source: child }));
  });
  vi.spyOn(child, "postMessage").mockImplementation((message, targetOrigin) => {
    expect(targetOrigin).toBe(FRED_ORIGIN);
    const deliver = () =>
      child.dispatchEvent(new MessageEvent("message", { data: message, origin: FRED_ORIGIN, source: host }));
    deliver();
    if (options.duplicateResponses && (message as { type?: string }).type?.startsWith("fred:response")) deliver();
  });

  client = createPackedClient(child);
  let context: Awaited<ReturnType<PackedClient["connect"]>> | undefined;
  await act(async () => {
    context = await client?.connect();
  });
  if (!context) throw new Error("integration setup: packed client did not connect");
  return { child, client, context };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

afterEach(async () => {
  client?.dispose();
  if (root) await act(async () => root?.unmount());
  container?.remove();
  client = undefined;
  root = undefined;
  container = undefined;
  vi.restoreAllMocks();
});

beforeEach(() => {
  h.appId = "example";
  h.navigate.mockReset();
  h.request.mockReset();
  h.subPath = "";
  h.teamId = "team-1";
  h.teamName = "Team One";
  h.agents = [];
  h.result.data.items[0].ui_prefix = "/apps/example-ui/";
});

integration("actual packed SDK with the production FRED host page", () => {
  it("connects, preserves route events, and sends navigation and open-chat intents", async () => {
    const connected = await connectPackedSdk();
    expect(connected.context.team.id).toBe("team-1");
    expect(connected.context.route.subPath).toBe("");

    const routes: string[] = [];
    connected.client.onRoute(({ subPath }) => routes.push(subPath));
    h.subPath = "A";
    await rerender();
    connected.client.navigate("B", { replace: true });
    expect(h.navigate).toHaveBeenCalledWith("/team/team-1/apps/example/B", { replace: true });
    h.subPath = "B";
    await rerender();
    h.subPath = "A";
    await rerender();

    connected.client.openChat();
    await flush();
    expect(routes).toEqual(["A", "A"]);
    expect(h.navigate).toHaveBeenCalledWith("/team/team-1/agents");
  });

  it("correlates successful, HTTP-error, transport, bodyless, and duplicate responses", async () => {
    const pendingResolvers: Array<(response: Response) => void> = [];
    h.request.mockImplementation((path: string) => {
      if (path === "success") return Promise.resolve(new Response('{"ok":true}', { status: 200 }));
      if (path === "http-error") return Promise.resolve(new Response("unavailable", { status: 503 }));
      if (path === "bodyless") return Promise.resolve(new Response(null, { status: 204 }));
      if (path === "transport") return Promise.reject(new Error("upstream detail"));
      return new Promise<Response>((resolve) => pendingResolvers.push(resolve));
    });
    const connected = await connectPackedSdk({ duplicateResponses: true });

    expect(await (await connected.client.request("success")).json()).toEqual({ ok: true });
    const httpError = await connected.client.request("http-error");
    expect([httpError.ok, httpError.status, await httpError.text()]).toEqual([false, 503, "unavailable"]);
    await expect(connected.client.request("transport")).rejects.toMatchObject({ code: "transport-error" });
    const bodyless = await connected.client.request("bodyless");
    expect([bodyless.status, await bodyless.text()]).toEqual([204, ""]);

    const first = connected.client.request("first");
    const second = connected.client.request("second");
    pendingResolvers[1]?.(new Response("second"));
    pendingResolvers[0]?.(new Response("first"));
    expect(await (await second).text()).toBe("second");
    expect(await (await first).text()).toBe("first");
  });

  it.each([
    [
      "frame target",
      () => {
        h.result.data.items[0].ui_prefix = "https://replacement.example/app/";
      },
    ],
    [
      "team",
      () => {
        h.teamId = "team-2";
        h.teamName = "Team Two";
      },
    ],
  ])("enforces pending capacity and rejects stale frame traffic after %s replacement", async (_kind, replace) => {
    h.request.mockReturnValue(new Promise<Response>(() => undefined));
    const connected = await connectPackedSdk();
    const pending = Array.from({ length: 16 }, (_, index) => connected.client.request(`pending-${index}`));
    await expect(connected.client.request("overflow")).rejects.toMatchObject({ code: "request-capacity" });
    expect(h.request).toHaveBeenCalledTimes(16);
    const oldSignals = h.request.mock.calls.map((call) => (call[1] as RequestInit).signal as AbortSignal);

    replace();
    await rerender();
    expect(oldSignals.every((signal) => signal.aborted)).toBe(true);
    h.navigate.mockClear();
    connected.client.navigate("stale");
    expect(h.navigate).not.toHaveBeenCalled();

    connected.client.dispose();
    await Promise.allSettled(pending);
  });
});
