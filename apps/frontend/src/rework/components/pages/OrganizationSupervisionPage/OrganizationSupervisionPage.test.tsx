// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { OrganizationSupervision, SupervisionCounts } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  OrganizationSupervisionAccessProvider,
  useOrganizationSupervisionAccess,
} from "@core/hooks/useOrganizationSupervisionAccess";
import OrganizationSupervisionPage from "./OrganizationSupervisionPage";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "token",
    GetSessionIdentity: () => "fixture/owner",
    ensureFreshToken: vi.fn().mockResolvedValue(true),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
const counts: SupervisionCounts = {
  active: { documents: 7, bytes: 100 },
  pending_purge: { documents: 0, bytes: 0 },
  published: {
    documents: 7,
    vectors: 9,
    chunks: 9,
    tabular_datasets: 0,
    total_rows: 0,
    known_rows: 0,
    datasets_with_unknown_rows: 0,
  },
  direct_roles: [],
  distinct_users: 1,
  failed_documents: 0,
  processing: [],
};
const summary = (organization_id = "org"): OrganizationSupervision => ({
  organization_id,
  active_teams: 1,
  collection_started_at: "2026-10-24T10:00:00Z",
  collection_finished_at: "2026-10-24T10:00:01Z",
  totals: counts,
  organization_direct: counts,
  teams_total: counts,
  personal_total: counts,
  teams: { items: [{ id: "team", name: `Team ${organization_id}`, counts }], next_cursor: null },
});
const detail = () => ({ ...summary(), team: summary().teams.items[0] });
const NativeRequest = globalThis.Request;
let requests: { path: string; body?: unknown; resolve: (response: Response) => void; reject: (error: Error) => void }[];
let store: ReturnType<typeof makeStore>;
let container: HTMLDivElement;
let root: Root;
let access: ReturnType<typeof useOrganizationSupervisionAccess>;
function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (getDefault) => getDefault().concat(api.middleware),
  });
}
function AccessProbe() {
  access = useOrganizationSupervisionAccess();
  return null;
}
async function waitFor(check: () => void) {
  await vi.waitFor(async () => {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    check();
  });
}
async function reply(path: string, data: unknown, status = 200) {
  await waitFor(() => expect(requests.some((request) => request.path === path)).toBe(true));
  const [request] = requests.splice(
    requests.findIndex((request) => request.path === path),
    1,
  );
  await act(async () =>
    request.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } })),
  );
}
async function authorize(org = "org") {
  await reply("/me/spaces", [{ id: org, organization_id: org }]);
  await waitFor(() =>
    expect(requests.find((request) => request.path === "/authorize/space")?.body).toEqual({
      space_id: org,
      permission: "own_organization",
    }),
  );
  expect(requests.filter((request) => request.path.includes("supervision"))).toHaveLength(0);
  await reply("/authorize/space", { allowed: true });
}
function click(label: string) {
  const button = [...container.querySelectorAll("button")].find((node) => node.textContent === label)!;
  expect(button).toBeDefined();
  expect(button.disabled).toBe(false);
  act(() => button.click());
}
async function denied() {
  await waitFor(() => expect(access.allowed).toBe(false));
  expect(container.textContent).toContain("rework.supervision.forbidden");
  expect(container.textContent).not.toContain("rework.supervision.totals");
}
async function loaded(org = "org") {
  await waitFor(() => expect(container.textContent).toContain(`Team ${org}`));
  expect(access.allowed).toBe(true);
}
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  requests = [];
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  vi.stubGlobal("fetch", async (request: Request) => {
    const body = request.method === "POST" ? await request.json() : undefined;
    return new Promise<Response>((resolve, reject) =>
      requests.push({ path: new URL(request.url).pathname.replace("/control-plane/v1", ""), body, resolve, reject }),
    );
  });
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <Provider store={store}>
        <OrganizationSupervisionAccessProvider>
          <AccessProbe />
          <OrganizationSupervisionPage />
        </OrganizationSupervisionAccessProvider>
      </Provider>,
    ),
  );
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
});

it.each([401, 403])(
  "recovers from cached summary %s after one refresh and still revokes on a new refusal",
  async (status) => {
    await authorize();
    await reply("/organizations/org/supervision", {}, status);
    if (status === 401) await reply("/organizations/org/supervision", {}, status);
    await denied();
    expect(api.endpoints.organizationSupervision.select({ organizationId: "org" })(store.getState()).status).toBe(
      "rejected",
    );
    click("rework.supervision.refresh");
    await authorize();
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(access.allowed).toBe(true);
    await reply("/organizations/org/supervision", summary());
    await loaded();
    click("rework.supervision.refresh");
    await authorize();
    await reply("/organizations/org/supervision", {}, status);
    if (status === 401) await reply("/organizations/org/supervision", {}, status);
    await denied();
  },
);
it("ignores a historical team refusal when reopening detail after renewed authorization", async () => {
  await authorize();
  await reply("/organizations/org/supervision", summary());
  await loaded();
  click("Team org");
  await reply("/organizations/org/supervision/teams/team", {}, 403);
  await denied();
  click("rework.supervision.refresh");
  await authorize();
  await reply("/organizations/org/supervision", summary());
  await loaded();
  expect(api.endpoints.teamSupervision.select({ organizationId: "org", teamId: "team" })(store.getState()).status).toBe(
    "rejected",
  );
  click("Team org");
  await reply("/organizations/org/supervision/teams/team", detail());
  await waitFor(() =>
    expect(container.querySelector('aside[aria-hidden="false"]')?.textContent).toContain(
      "rework.supervision.publishedDocuments",
    ),
  );
  expect(access.allowed).toBe(true);
  // Focus rechecks context/permission before resuming both open subscriptions.
  act(() => window.dispatchEvent(new Event("focus")));
  await authorize();
  await reply("/organizations/org/supervision", summary());
  await reply("/organizations/org/supervision/teams/team", {}, 403);
  await denied();
});
it.each([200, 403])("ignores a late old-organization response (%s) after focus changes context", async (status) => {
  await authorize();
  await waitFor(() => expect(requests.some((request) => request.path === "/organizations/org/supervision")).toBe(true));
  const [late] = requests.splice(0, 1);
  act(() => window.dispatchEvent(new Event("focus")));
  await authorize("other");
  await reply("/organizations/other/supervision", summary("other"));
  await loaded("other");
  await act(async () => late.resolve(new Response(JSON.stringify(summary()), { status })));
  await waitFor(() =>
    expect(api.endpoints.organizationSupervision.select({ organizationId: "org" })(store.getState()).status).toBe(
      status === 200 ? "fulfilled" : "rejected",
    ),
  );
  expect(access.allowed).toBe(true);
  expect(container.textContent).not.toContain("Team org");
  expect(container.textContent).toContain("Team other");
});
it.each([503, "network"])("keeps %s as a loading failure without revocation or zero metrics", async (failure) => {
  await authorize();
  if (failure === 503) await reply("/organizations/org/supervision", {}, 503);
  else {
    await waitFor(() => expect(requests).toHaveLength(1));
    await act(async () => requests.shift()!.reject(new Error("offline")));
  }
  await waitFor(() =>
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      failure === 503 ? "dependencyUnavailable" : "loadFailed",
    ),
  );
  expect(access.allowed).toBe(true);
  expect(container.textContent).not.toContain("rework.supervision.totals");
});
