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

const h = vi.hoisted(() => ({
  appId: "example" as string | undefined,
  isPersonalTeam: false,
  navigate: vi.fn(),
  request: vi.fn(),
  subPath: "",
  uiPrefix: "/apps/example-ui/",
  result: { data: undefined, isLoading: false, isError: false } as {
    data?: { items: Array<Record<string, unknown>> };
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en" },
  }),
}));
vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1", appId: h.appId, "*": h.subPath }),
  useNavigate: () => h.navigate,
}));
vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({
    teamId: "team-1",
    isPersonalTeam: h.isPersonalTeam,
    selectedTeam: { id: "team-1", name: "Team One" },
  }),
}));
vi.mock("@rework/features/applications/useTeamApplications.ts", () => ({
  useTeamApplications: () => h.result,
}));
vi.mock("@rework/features/applications/applicationRequest.ts", () => ({
  createApplicationRequest: () => h.request,
}));

import TeamApplicationHostPage, { APPLICATION_HANDSHAKE_TIMEOUT_MS } from "./TeamApplicationHostPage.tsx";

const FRED_ORIGIN = "http://localhost:3000";

function application() {
  return {
    id: "example",
    version: "1.0.0",
    name: { en: "Example App", fr: "Application exemple" },
    description: { en: "An example", fr: "Un exemple" },
    icon: "extension",
    ui_prefix: h.uiPrefix,
  };
}

function withUiPrefix(uiPrefix: string) {
  h.uiPrefix = uiPrefix;
  h.result.data = { items: [application()] };
}

let container: HTMLDivElement | undefined;
let root: Root | undefined;

beforeAll(() => {
  // Serve the frame document locally: without this happy-dom tries to fetch
  // the iframe src over the network and dumps a connection error per test.
  const settings = (globalThis as unknown as { happyDOM?: { settings?: { fetch?: Record<string, unknown> } } }).happyDOM
    ?.settings;
  if (settings?.fetch) {
    settings.fetch.interceptor = {
      beforeAsyncRequest: async () =>
        new Response("<!doctype html><title>app</title>", { headers: { "content-type": "text/html" } }),
    };
  }
});

async function renderPage() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await rerender();
  return container;
}

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

function frame(): HTMLIFrameElement | null {
  return container?.querySelector("iframe") ?? null;
}

function frameWindow(): Window {
  const contentWindow = frame()?.contentWindow;
  if (!contentWindow) throw new Error("test setup: the frame has no content window");
  return contentWindow;
}

function spyOnFrame() {
  return vi.spyOn(frameWindow(), "postMessage").mockImplementation(() => undefined);
}

async function postFromFrame(data: unknown, source: unknown = frameWindow()) {
  await act(async () => {
    window.dispatchEvent(new MessageEvent("message", { data, source: source as Window, origin: FRED_ORIGIN }));
    await Promise.resolve();
  });
}

function postedMessages(spy: ReturnType<typeof spyOnFrame>) {
  return spy.mock.calls.map((call) => call[0] as Record<string, unknown>);
}

/** Render, then complete a successful v1 handshake. Returns the frame spy. */
async function connect() {
  await renderPage();
  const spy = spyOnFrame();
  await postFromFrame({ type: "fred:ready", protocolVersion: "1" });
  return spy;
}

afterEach(() => {
  if (root) act(() => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
  vi.restoreAllMocks();
  vi.useRealTimers();
});

beforeEach(() => {
  h.appId = "example";
  h.isPersonalTeam = false;
  h.navigate.mockReset();
  h.request.mockReset();
  h.subPath = "";
  h.uiPrefix = "/apps/example-ui/";
  h.result = { data: { items: [application()] }, isLoading: false, isError: false };
});

describe("TeamApplicationHostPage frame admission", () => {
  it("points the frame at the catalog's configured prefix, not one derived from the id", async () => {
    await renderPage();

    expect(frame()?.getAttribute("src")).toBe(`${FRED_ORIGIN}/apps/example-ui/`);
  });

  it("keeps a frame served from another origin on that origin", async () => {
    withUiPrefix("https://apps.example/example/");

    await renderPage();
    const spy = spyOnFrame();
    await postFromFrame({ type: "fred:ready", protocolVersion: "1" });

    expect(frame()?.getAttribute("src")).toBe("https://apps.example/example/");
    expect(spy.mock.calls[0]?.[1]).toBe("https://apps.example");
  });

  it("never builds a frame for an application the catalog did not authorize", async () => {
    h.appId = "other";

    const page = await renderPage();

    expect(page.textContent).toContain("teamAppsPage.host.unavailable");
    expect(frame()).toBeNull();
  });

  it("never builds a frame for a personal space", async () => {
    h.isPersonalTeam = true;

    const page = await renderPage();

    expect(page.textContent).toContain("teamAppsPage.host.unavailable");
    expect(frame()).toBeNull();
  });

  it("refuses a configured prefix that is not http(s)", async () => {
    withUiPrefix("javascript:alert(1)");

    const page = await renderPage();

    expect(page.textContent).toContain("teamAppsPage.host.unavailable");
    expect(frame()).toBeNull();
  });
});

describe("TeamApplicationHostPage protocol handshake", () => {
  it("sends the context only after the frame announces an accepted version", async () => {
    await renderPage();
    const spy = spyOnFrame();

    expect(spy).not.toHaveBeenCalled();

    await postFromFrame({ type: "fred:ready", protocolVersion: "1" });

    expect(postedMessages(spy)).toEqual([
      {
        type: "fred:context",
        protocolVersion: "1",
        applicationId: "example",
        context: {
          team: { id: "team-1", name: "Team One", isPersonal: false },
          route: { basePath: "/team/team-1/apps/example", subPath: "" },
          locale: "en",
        },
      },
    ]);
    expect(spy.mock.calls[0]?.[1]).toBe(FRED_ORIGIN);
  });

  it("shows the mismatch state and never marks a frame ready on an unsupported version", async () => {
    const page = await renderPage();
    const spy = spyOnFrame();

    await postFromFrame({ type: "fred:ready", protocolVersion: "2" });

    expect(page.textContent).toContain("teamAppsPage.host.protocol-mismatch");
    expect(spy).not.toHaveBeenCalled();
    expect(frame()).toBeNull();
  });

  it("reports an unreachable frame when the handshake never arrives", async () => {
    vi.useFakeTimers();
    const page = await renderPage();

    await act(async () => {
      vi.advanceTimersByTime(APPLICATION_HANDSHAKE_TIMEOUT_MS);
    });

    expect(page.textContent).toContain("teamAppsPage.host.unreachable");
    expect(frame()).toBeNull();
  });

  it.each([
    ["a foreign message type", { type: "fred:teleport", protocolVersion: "1" }],
    ["a ready with no version", { type: "fred:ready" }],
    ["a ready with a structured version", { type: "fred:ready", protocolVersion: { toString: "1" } }],
    ["a bare string", "fred:ready"],
    ["null", null],
  ])("ignores %s without answering or changing state", async (_name, payload) => {
    const page = await renderPage();
    const spy = spyOnFrame();

    await postFromFrame(payload);

    expect(spy).not.toHaveBeenCalled();
    expect(page.textContent).toContain("teamAppsPage.host.connecting");
    expect(frame()).not.toBeNull();
  });

  it("ignores a valid handshake sent by a window that is not the frame", async () => {
    const page = await renderPage();
    const spy = spyOnFrame();

    await postFromFrame({ type: "fred:ready", protocolVersion: "1" }, window);

    expect(spy).not.toHaveBeenCalled();
    expect(page.textContent).toContain("teamAppsPage.host.connecting");
  });
});

describe("TeamApplicationHostPage routing", () => {
  it("hands a deep-linked sub-path to the frame in the opening context", async () => {
    h.subPath = "reports/7";

    const spy = await connect();

    const context = postedMessages(spy)[0]?.context as { route: { basePath: string; subPath: string } };
    expect(context.route).toEqual({ basePath: "/team/team-1/apps/example", subPath: "reports/7" });
  });

  it("turns a frame navigation into a Fred route change", async () => {
    await connect();

    await postFromFrame({ type: "fred:navigate", path: "reports/9", replace: true });

    expect(h.navigate).toHaveBeenCalledWith("/team/team-1/apps/example/reports/9", { replace: true });
  });

  it("refuses a frame navigation that escapes the application's own subtree", async () => {
    await connect();

    await postFromFrame({ type: "fred:navigate", path: "../../settings" });
    await postFromFrame({ type: "fred:navigate", path: "/team/team-2/agents" });

    expect(h.navigate).not.toHaveBeenCalled();
  });

  it("pushes a Fred-side route change down, but does not echo the frame's own", async () => {
    const spy = await connect();
    spy.mockClear();

    await postFromFrame({ type: "fred:navigate", path: "reports/9" });
    h.subPath = "reports/9";
    await rerender();

    expect(postedMessages(spy)).toEqual([]);

    h.subPath = "reports/12";
    await rerender();

    expect(postedMessages(spy)).toEqual([{ type: "fred:route", subPath: "reports/12" }]);
  });
});

describe("TeamApplicationHostPage service proxying", () => {
  it("answers a frame request through Fred's authenticated transport", async () => {
    h.request.mockResolvedValue(
      new Response('{"ok":true}', { status: 201, headers: { "content-type": "application/json" } }),
    );
    const spy = await connect();
    spy.mockClear();

    await postFromFrame({
      type: "fred:request",
      requestId: "r1",
      path: "reports?page=2",
      method: "POST",
      headers: { "content-type": "application/json" },
      body: '{"a":1}',
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(h.request).toHaveBeenCalledOnce();
    const [path, init] = h.request.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("reports?page=2");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(init.body).toBe('{"a":1}');
    expect(init.signal).toBeInstanceOf(AbortSignal);

    expect(postedMessages(spy)).toEqual([
      {
        type: "fred:response",
        requestId: "r1",
        status: 201,
        headers: { "content-type": "application/json" },
        body: '{"ok":true}',
      },
    ]);
  });

  it("reports a failed call without repeating what the transport said", async () => {
    h.request.mockRejectedValue(new Error("application domain payload"));
    const spy = await connect();
    spy.mockClear();

    await postFromFrame({ type: "fred:request", requestId: "r2", path: "reports" });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const posted = postedMessages(spy);
    expect(posted).toEqual([{ type: "fred:response-error", requestId: "r2" }]);
    expect(JSON.stringify(posted)).not.toContain("application domain payload");
  });

  it("never issues a call for a request the schema rejects", async () => {
    await connect();

    await postFromFrame({ type: "fred:request", requestId: "r3", path: "reports", method: "TRACE" });
    await postFromFrame({ type: "fred:request", path: "reports" });

    expect(h.request).not.toHaveBeenCalled();
  });
});
