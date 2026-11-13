// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AnalyticsRequest, AnalyticsResponse, MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  organizationId: "Acme" as string | undefined,
  identity: "alice",
  loading: false,
  error: undefined as unknown,
  memberships: [] as MySpace[],
}));
vi.mock("@core/hooks/useWorkingOrganization", () => ({
  useWorkingOrganization: () => ({
    organizationId: h.organizationId,
    loading: h.loading,
    error: h.error,
    memberships: { currentData: h.memberships },
  }),
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetSessionIdentity: () => h.identity,
    GetToken: () => h.identity,
    ensureFreshToken: async () => true,
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { pct?: string; abs?: string }) =>
      `${key}${values?.abs ? `:${values.pct}:${values.abs}` : ""}`,
    i18n: { language: "en" },
  }),
}));
vi.mock("./ResponsibleAiSection/ResponsibleAiSection.tsx", () => ({ default: () => null }));
vi.mock("./RecentAgents/RecentAgents.tsx", () => ({ default: () => null }));
vi.mock("./HomeSearch/HomeSearch.tsx", () => ({ default: () => null }));
vi.mock("./MarketplaceTopPrompts/MarketplaceTopPrompts.tsx", () => ({ default: () => null }));
import { controlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { ActivityTab } from "./HomePage";

const NativeRequest = globalThis.Request;
let root: Root;
let host: HTMLDivElement;
let store: ReturnType<typeof makeStore>;
function makeStore() {
  return configureStore({ reducer: { [api.reducerPath]: api.reducer }, middleware: (d) => d().concat(api.middleware) });
}
function reply(body: AnalyticsRequest, count = "12"): AnalyticsResponse {
  return {
    calculation: "exact",
    collection_completeness: "unknown",
    results: Object.fromEntries(
      body.queries.map((q) => [
        q.name,
        {
          ...q.time,
          measures: [],
          truncated: q.name === "agents",
          rows: q.group_by?.length
            ? []
            : [
                {
                  dimensions: { kind: "total" },
                  values: Object.fromEntries(q.measures.map((m) => [m, q.name === "previous" ? "0" : count])),
                },
              ],
        },
      ]),
    ),
  };
}
function render(period: 7 | 30 | 90 = 30) {
  root.render(
    <Provider store={store}>
      <ActivityTab period={period} />
    </Provider>,
  );
}
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  h.organizationId = "Acme";
  h.identity = "alice";
  h.loading = false;
  h.error = undefined;
  h.memberships = [];
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  host = document.createElement("div");
  root = createRoot(host);
  store = makeStore();
});
afterEach(async () => {
  await act(async () => root.unmount());
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
});

it.each([7, 30, 90] as const)(
  "uses equal adjacent %s-day windows and one shared historical request",
  async (period) => {
    const requests: AnalyticsRequest[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        const body = (await request.json()) as AnalyticsRequest;
        requests.push(body);
        expect(request.method).toBe("POST");
        expect(new URL(request.url).pathname).toBe("/control-plane/v1/analytics/query");
        expect(Object.keys(body)).toEqual(["queries"]);
        return new Response(JSON.stringify(reply(body, "9007199254740993")));
      }),
    );
    await act(async () => render(period));
    await act(async () => {
      await vi.waitFor(() => expect(host.textContent).toContain("9,007,199,254,740,993"));
    });
    expect(requests).toHaveLength(2);
    for (const request of requests) {
      const current = request.queries.find((q) => q.name === "current")!;
      const previous = request.queries.find((q) => q.name === "previous")!;
      expect(previous.time.until).toBe(current.time.since);
      expect(Date.parse(current.time.until) - Date.parse(current.time.since)).toBe(period * 86400000);
      expect(Date.parse(previous.time.until) - Date.parse(previous.time.since)).toBe(period * 86400000);
      expect(request.queries.every((q) => q.scope.kind === "self" && q.scope.organization_id === "Acme")).toBe(true);
    }
    expect(requests.find((r) => r.queries.length === 4)?.queries.map((q) => q.name)).toEqual([
      "current",
      "previous",
      "teams",
      "agents",
    ]);
    expect(host.textContent).toContain("+9,007,199,254,740,993");
    expect(host.textContent).toContain("rework.home.activity.truncated");
  },
);

it("never replaces Globex with late Acme results and isolates a changed identity", async () => {
  const releases: (() => void)[] = [];
  const fetch = vi.fn(async (request: Request) => {
    const body = (await request.json()) as AnalyticsRequest;
    const scope = body.queries[0].scope;
    const acme = scope.kind === "self" && scope.organization_id === "Acme";
    if (acme) await new Promise<void>((resolve) => releases.push(resolve));
    return new Response(
      JSON.stringify(
        reply(body, acme ? "11111" : request.headers.get("Authorization") === "Bearer bob" ? "33333" : "22222"),
      ),
    );
  });
  vi.stubGlobal("fetch", fetch);
  await act(async () => render());
  await vi.waitFor(() => expect(releases).toHaveLength(2));
  expect(host.textContent).toContain("rework.home.activity.loading");
  h.organizationId = "Globex";
  await act(async () => render());
  await act(async () => {
    await vi.waitFor(() => expect(host.textContent).toContain("22,222"));
  });
  await act(async () => {
    releases.forEach((release) => release());
    await new Promise((r) => setTimeout(r, 20));
  });
  expect(host.textContent).not.toContain("11,111");
  h.identity = "bob";
  await act(async () => render());
  await act(async () => {
    await vi.waitFor(() => expect(host.textContent).toContain("33,333"));
  });
  expect(host.textContent).not.toContain("22,222");
  h.error = new Error("revoked");
  await act(async () => render());
  expect(host.textContent).not.toContain("33,333");
  expect(host.textContent).toContain("rework.home.activity.error");
  expect(fetch).toHaveBeenCalledTimes(6);
});

it.each([403, 503])("does not turn an analytics %s into stable, zero or no memberships", async (status) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ error: "unavailable" }), { status })),
  );
  await act(async () => render());
  const label = status === 503 ? "unavailable" : "error";
  await act(async () => {
    await vi.waitFor(() => expect(host.textContent).toContain(`rework.home.activity.${label}`));
  });
  expect(host.textContent).not.toContain("rework.home.activity.deltaFlat");
  expect(host.textContent).not.toContain("rework.home.topTeams.empty");
  expect(host.textContent).not.toContain("rework.home.topAgents.empty");
});

it("skips analytics without a valid organization", async () => {
  h.organizationId = undefined;
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  await act(async () => render());
  expect(fetch).not.toHaveBeenCalled();
  expect(host.textContent).toContain("rework.home.activity.organizationRequired");
  expect(host.textContent).not.toContain("rework.home.activity.deltaFlat");
});

it("shows observed zeros and empty rankings only after successful reads", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const body = (await request.json()) as AnalyticsRequest;
      return new Response(JSON.stringify(reply(body, "0")));
    }),
  );
  await act(async () => render());
  await act(async () => {
    await vi.waitFor(() => expect(host.textContent).toContain("rework.home.activity.deltaFlat"));
  });
  expect(host.textContent).toContain("rework.home.topTeams.empty");
  expect(host.textContent).toContain("rework.home.topAgents.empty");
  expect(host.textContent).not.toContain("rework.home.activity.unavailable");
});

it("does not invent a stable comparison when previous counts are absent", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const body = (await request.json()) as AnalyticsRequest;
      const data = reply(body, "12");
      data.results.previous.rows = [];
      return new Response(JSON.stringify(data));
    }),
  );
  await act(async () => render());
  await act(async () => {
    await vi.waitFor(() => expect(host.textContent).toContain("rework.home.topAgents.empty"));
  });
  expect(host.textContent).not.toContain("rework.home.activity.deltaFlat");
  expect(host.textContent).not.toContain("rework.home.activity.deltaUp");
});
