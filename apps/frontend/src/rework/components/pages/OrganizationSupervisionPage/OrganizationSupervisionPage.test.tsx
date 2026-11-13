// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  MySpace,
  OrganizationSupervision,
  SupervisionCounts,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  OrganizationSupervisionAccessProvider,
  useOrganizationSupervisionAccess,
} from "@core/hooks/useOrganizationSupervisionAccess";
import OrganizationSupervisionPage from "./OrganizationSupervisionPage";
import AdminNavbar from "../../shared/layouts/Sidebar/AdminNavbar/AdminNavbar";
import { useOrganizationOwner } from "@core/hooks/useOrganizationOwner";
import { WorkingOrganizationProvider, useWorkingOrganization } from "@core/hooks/useWorkingOrganization";

vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => ({ isAdmin: false }) }));
vi.mock("@hooks/useUserCapabilities.ts", () => ({ useUserCapabilities: () => ({}) }));
vi.mock("../../../../common/config", () => ({ getConfig: () => ({ platform_access_enabled: false }) }));
vi.mock("../../../features/tasks/taskSlice", () => ({ selectActiveCount: () => 0 }));

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
const membership = (id: string, roles: MySpace["roles"] = ["organization_admin", "owner"]): MySpace => ({
  id,
  organization_id: id,
  kind: "organization",
  name: id,
  roles,
  parent_id: null,
  personal_owner: null,
  path: [id],
});
const preferenceKey = "working.organization:fixture/owner";
let working: ReturnType<typeof useWorkingOrganization>;
const NativeRequest = globalThis.Request;
let requests: {
  search: string;
  path: string;
  body?: unknown;
  resolve: (response: Response) => void;
  reject: (error: Error) => void;
}[];
let store: ReturnType<typeof makeStore>;
let container: HTMLDivElement;
let root: Root;
let access: ReturnType<typeof useOrganizationSupervisionAccess>;
let owner: ReturnType<typeof useOrganizationOwner>;
function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (getDefault) => getDefault().concat(api.middleware),
  });
}
function AccessProbe() {
  working = useWorkingOrganization();
  access = useOrganizationSupervisionAccess();
  owner = useOrganizationOwner();
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
  await reply("/me/spaces", [membership(org)]);
  await waitFor(() => expect(working.loading).toBe(false));
  if (working.organizationId !== org) chooseOrganization(org);
  await waitFor(() =>
    expect(requests.find((request) => request.path === "/authorize/space")?.body).toEqual({
      space_id: org,
      permission: "administer_organization",
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
  sessionStorage.clear();
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
    if (new URL(request.url).pathname.endsWith("/me/marketplaces"))
      return new Response(JSON.stringify({ items: [], next_cursor: null }), {
        headers: { "Content-Type": "application/json" },
      });
    const body = request.method === "POST" ? await request.json() : undefined;
    return new Promise<Response>((resolve, reject) =>
      requests.push({
        path: new URL(request.url).pathname.replace("/control-plane/v1", ""),
        search: new URL(request.url).search,
        body,
        resolve,
        reject,
      }),
    );
  });
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  render();
});
function render() {
  act(() =>
    root.render(
      <Provider store={store}>
        <MemoryRouter initialEntries={["/admin/supervision"]}>
          <WorkingOrganizationProvider>
            <OrganizationSupervisionAccessProvider>
              <AccessProbe />
              <AdminNavbar />
              <OrganizationSupervisionPage />
            </OrganizationSupervisionAccessProvider>
          </WorkingOrganizationProvider>
        </MemoryRouter>
      </Provider>,
    ),
  );
}
function chooseOrganization(name: string) {
  act(() => {
    expect(working.selectOrganization(name)).toBe(true);
  });
}
async function decision(org: string, allowed = true) {
  await waitFor(() =>
    expect(requests.find((request) => request.path === "/authorize/space")?.body).toEqual({
      space_id: org,
      permission: "administer_organization",
    }),
  );
  await reply("/authorize/space", { allowed });
}

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

it("switches the header, rights and requests together, resets team/cursors and ignores late data", async () => {
  await reply("/me/spaces", [
    membership("Acme"),
    membership("Globex", ["organization_admin"]),
    membership("Hidden", ["member"]),
  ]);
  await decision("Acme");
  await reply("/organizations/Acme/supervision", {
    ...summary("Acme"),
    teams: { ...summary("Acme").teams, next_cursor: "acme-next" },
  });
  await loaded("Acme");
  expect(owner.organizationId).toBe("Acme");
  expect(container.querySelector('a[href="/admin/features"]')).not.toBeNull();
  click("Team Acme");
  await waitFor(() => expect(requests.some((r) => r.path.endsWith("/teams/team"))).toBe(true));
  click("dataTable.pagination.next");
  await waitFor(() => expect(requests.some((r) => r.search.includes("acme-next"))).toBe(true));
  const late = requests.splice(0);
  chooseOrganization("Globex");
  expect(container.querySelector("h2")?.previousElementSibling?.textContent).toContain("Globex");
  expect(owner.isOwner).toBe(false);
  expect(owner.organizationId).toBeUndefined();
  expect(container.querySelector('a[href="/admin/features"]')).toBeNull();
  expect(container.textContent).not.toContain("Team Acme");
  await decision("Globex");
  await waitFor(() => expect(requests).toHaveLength(1));
  expect(requests[0].path).toBe("/organizations/Globex/supervision");
  expect(requests[0].search).toBe("");
  await reply("/organizations/Globex/supervision", summary("Globex"));
  await loaded("Globex");
  await act(async () => {
    for (const request of late)
      request.resolve(
        new Response(
          JSON.stringify(
            request.path.endsWith("/teams/team")
              ? { ...summary("Acme"), team: summary("Acme").teams.items[0] }
              : summary("Acme"),
          ),
        ),
      );
  });
  await waitFor(() =>
    expect(
      api.endpoints.organizationSupervision.select({ organizationId: "Acme", after: "acme-next" })(store.getState())
        .status,
    ).toBe("fulfilled"),
  );
  expect(container.textContent).not.toContain("Team Acme");
  expect(container.querySelector('aside[aria-hidden="false"]')).toBeNull();
  expect(access.allowed).toBe(true);
  // Switching back also discards pagination and rechecks permission before cached data can appear.
  chooseOrganization("Acme");
  expect(container.textContent).not.toContain("Team Acme");
  await decision("Acme");
  await waitFor(() => expect(requests).toHaveLength(1));
  expect(requests[0].search).toBe("");
});

it("restores a selection on reload and never switches organizations when its admin role is revoked", async () => {
  await reply("/me/spaces", [membership("Acme"), membership("Globex")]);
  await decision("Acme");
  await reply("/organizations/Acme/supervision", summary("Acme"));
  await loaded("Acme");
  chooseOrganization("Globex");
  await decision("Globex");
  await reply("/organizations/Globex/supervision", summary("Globex"));
  await loaded("Globex");
  expect(sessionStorage.getItem(preferenceKey)).toBe("Globex");
  act(() => root.render(null));
  store.dispatch(api.util.resetApiState());
  store = makeStore();
  render();
  await reply("/me/spaces", [membership("Acme"), membership("Globex")]);
  await decision("Globex");
  await reply("/organizations/Globex/supervision", summary("Globex"));
  await loaded("Globex");
  act(() => window.dispatchEvent(new Event("focus")));
  await reply("/me/spaces", [membership("Acme"), membership("Globex", ["member"])]);
  await decision("Globex", false);
  await denied();
  expect(working.organizationId).toBe("Globex");
  expect(owner.isOwner).toBe(false);
  expect(requests).toHaveLength(0);
});

it("never promotes a selected member or child-space role to organization owner", async () => {
  act(() => root.render(null));
  sessionStorage.setItem(preferenceKey, "Hidden");
  render();
  await reply("/me/spaces", [
    membership("Hidden", ["member"]),
    { ...membership("team"), kind: "team" },
    membership("Acme"),
  ]);
  await decision("Hidden", false);
  await denied();
  expect(owner.isOwner).toBe(false);
  expect(working.organizationId).toBe("Hidden");
  chooseOrganization("team");
  expect(owner.isOwner).toBe(false);
  expect(access.organizationId).toBeUndefined();
  expect(requests).toHaveLength(0);
});

it("ignores a late authorization decision from the previous selection", async () => {
  await reply("/me/spaces", [membership("Acme"), membership("Globex")]);
  await waitFor(() => expect(requests.some((r) => r.path === "/authorize/space")).toBe(true));
  const late = requests.shift()!;
  chooseOrganization("Globex");
  await decision("Globex", false);
  await act(async () => late.resolve(new Response(JSON.stringify({ allowed: true }))));
  await denied();
  expect(access.organizationId).toBe("Globex");
  expect(requests).toHaveLength(0);
});

it("rechecks authorization when returning before the intervening organization's decision", async () => {
  await reply("/me/spaces", [membership("Acme"), membership("Globex")]);
  await decision("Acme");
  await reply("/organizations/Acme/supervision", summary("Acme"));
  await loaded("Acme");
  chooseOrganization("Globex");
  await waitFor(() => expect(requests.some((r) => r.path === "/authorize/space")).toBe(true));
  const late = requests.shift()!;
  chooseOrganization("Acme");
  expect(access.allowed).toBe(false);
  expect(container.textContent).not.toContain("Team Acme");
  await decision("Acme", false);
  await act(async () => late.resolve(new Response(JSON.stringify({ allowed: true }))));
  await denied();
  expect(access.organizationId).toBe("Acme");
  expect(requests).toHaveLength(0);
});
