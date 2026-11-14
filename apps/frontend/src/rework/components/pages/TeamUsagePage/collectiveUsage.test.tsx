// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { WorkingOrganizationProvider, useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import type { AnalyticsRequest, AnalyticsResponse, MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { TeamWithPermissions } from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TeamUsagePage from "./TeamUsagePage";

const h = vi.hoisted(() => ({
  identity: "alice",
  platformRoles: [] as string[],
  legacyTeam: undefined as TeamWithPermissions | undefined,
  legacy: vi.fn((_args: unknown, _options: unknown) => ({ isFetching: false, isLoading: false, isError: false })),
  t: (key: string) => key,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.t, i18n: { language: "en" } }) }));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetSessionIdentity: () => h.identity,
    GetToken: () => h.identity,
    GetUserId: () => h.identity,
    GetUserRoles: () => h.platformRoles,
    ensureFreshToken: async () => true,
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
// Swift is an independent boundary. No mock of Weaver authority, queries or cache.
vi.mock("../../../../hooks/useSelectedTeam", () => ({ useSelectedTeam: () => ({ selectedTeam: h.legacyTeam }) }));
vi.mock("../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useAgentsTotalQuery: h.legacy,
  useDocumentsTotalQuery: h.legacy,
  useSessionsOverTimeQuery: h.legacy,
  useStorageByTeamQuery: h.legacy,
  useTopAgentsByConversationsQuery: h.legacy,
  useSkillUsageQuery: h.legacy,
}));
// Only plotting is replaced; the precision adapter, counters and impact view run unchanged.
vi.mock("@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart", () => ({
  default: ({ rows }: { rows: unknown }) => <output>{JSON.stringify(rows)}</output>,
}));
vi.mock("@shared/molecules/BarChart/BarChart", () => ({
  default: ({ rows }: { rows: unknown }) => <output>{JSON.stringify(rows)}</output>,
}));
const fixed = { since: "2026-01-01T00:00:00Z", until: "2026-01-03T00:00:00Z" };
vi.mock("@shared/molecules/TimeRangeSelector/TimeRangeSelector", () => ({
  default: ({ onChange }: { onChange: (range: TimeRange) => void }) => (
    <button onClick={() => onChange(fixed)}>fixed-period</button>
  ),
}));

const space = (id: string, kind: MySpace["kind"], roles: MySpace["roles"], org = "Acme"): MySpace => ({
  id,
  kind,
  roles,
  organization_id: org,
  name: id,
  parent_id: kind === "organization" ? null : org,
  path: [org, id],
  personal_owner: kind === "personal" ? "alice" : null,
});
let memberships: MySpace[];
let membershipStatus: number;
let collectiveStatus: number;
let hold: string | undefined;
let release: (() => void) | undefined;
let requests: { body: AnalyticsRequest; actor: string | null }[];
let store: ReturnType<typeof makeStore>;
let root: Root;
let host: HTMLDivElement;
let context: ReturnType<typeof useWorkingOrganization>;
let navigate: ReturnType<typeof useNavigate>;
const NativeRequest = globalThis.Request;
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) => defaults().concat(api.middleware),
  });
}
function response(body: AnalyticsRequest, actor: string | null): AnalyticsResponse {
  const scope = body.queries[0].scope;
  const label = `${actor}/${scope.kind === "space" ? scope.id : scope.organization_id}/usage`;
  return {
    calculation: "mixed",
    collection_completeness: "unknown",
    results: Object.fromEntries(
      body.queries.map((query) => [
        query.name,
        {
          since: query.time.since,
          until: query.time.until,
          timezone: "UTC",
          measures: [],
          truncated: false,
          rows:
            query.name === "skills"
              ? []
              : [
                  {
                    dimensions:
                      query.name === "agents"
                        ? { kind: "agent", space_id: "team-a", agent_instance_id: "agent-a", display_name: label }
                        : query.name === "models"
                          ? { kind: "model", model_source_id: "source", upstream_model_id: label }
                          : query.name === "series"
                            ? { kind: "time", start: query.time.since }
                            : { kind: "total" },
                    values: {
                      "usage.total_tokens": "123",
                      "usage.input_tokens": "100",
                      "usage.output_tokens": "23",
                      "usage.cache_read_tokens": "30",
                      "usage.cache_creation_tokens": "5",
                    },
                  },
                ],
        },
      ]),
    ),
  };
}
function Controls() {
  context = useWorkingOrganization();
  navigate = useNavigate();
  return null;
}
function render() {
  act(() =>
    root.render(
      <Provider store={store}>
        <MemoryRouter initialEntries={["/team/team-a/usage"]}>
          <WorkingOrganizationProvider>
            <Controls />
            <Routes>
              <Route path="/team/:teamId/usage" element={<TeamUsagePage />} />
            </Routes>
          </WorkingOrganizationProvider>
        </MemoryRouter>
      </Provider>,
    ),
  );
}
async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
async function until(assertion: () => void) {
  await vi.waitFor(async () => {
    await flush();
    assertion();
  });
}
function collectiveRequests() {
  return requests.filter(({ body }) => body.queries[0].scope.kind === "space");
}
function click(label: string) {
  const button = [...host.querySelectorAll("button")].find(
    (item) => item.title === label || item.textContent === label,
  );
  expect(button).toBeDefined();
  act(() => button!.click());
}
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  h.identity = "alice";
  h.platformRoles = [];
  h.legacyTeam = undefined;
  h.legacy.mockClear();
  memberships = [space("Acme", "organization", ["member"]), space("team-a", "team", ["owner"])];
  membershipStatus = collectiveStatus = 200;
  hold = undefined;
  release = undefined;
  requests = [];
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith("/me/spaces")) return json(memberships, membershipStatus);
      if (path.endsWith("/me/marketplaces")) return json({ items: [], next_cursor: null });
      if (path.endsWith("/analytics/query")) {
        const body = (await request.clone().json()) as AnalyticsRequest;
        const actor = request.headers.get("authorization")?.replace("Bearer ", "") ?? null;
        requests.push({ body, actor });
        const scope = body.queries[0].scope;
        const reply = response(body, actor);
        const status = scope.kind === "space" ? collectiveStatus : 200;
        if (scope.kind === "space" && scope.id === hold) {
          hold = undefined;
          await new Promise<void>((resolve) => {
            release = resolve;
          });
        }
        return json(status === 200 ? reply : { code: status === 403 ? "forbidden" : "dependency_unavailable" }, status);
      }
      throw new Error(`Unexpected request: ${path}`);
    }),
  );
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  release?.();
  await flush();
  act(() => root.unmount());
  store.dispatch(api.util.resetApiState());
  host.remove();
  vi.unstubAllGlobals();
});

it.each(["owner", "analyst"] as const)(
  "admits direct %s without Swift bootstrap and sends one bounded batch",
  async (role) => {
    memberships[1].roles = [role];
    render();
    await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
    expect(collectiveRequests()).toHaveLength(1);
    const queries = collectiveRequests()[0].body.queries;
    expect(queries.map((query) => query.name)).toEqual(["total", "series", "agents", "models", "impact"]);
    for (const query of queries) {
      expect(query.scope).toEqual({ kind: "space", id: "team-a" });
      expect(query.time).toEqual(queries[0].time);
      expect(query.time.timezone).toBe("UTC");
      expect(Date.parse(query.time.until) - Date.parse(query.time.since)).toBeLessThanOrEqual(366 * 86400000);
    }
    expect(queries.filter((query) => query.limit).map((query) => query.limit)).toEqual([100, 100]);
    expect(host.textContent).toContain("rework.consumption.teamTitle");
    expect(host.textContent).toContain("rework.teamUsage.personalSectionTitle");
    expect(host.textContent).not.toContain("rework.teamUsage.team.sectionTitle");
    expect(host.textContent).not.toContain("rework.teamUsage.team.skillsSectionTitle");
    expect(h.legacy.mock.calls.every(([, options]) => (options as { skip: boolean }).skip)).toBe(true);
    render();
    await flush();
    expect(collectiveRequests()).toHaveLength(1);
  },
);

it.each(["member", "editor"] as const)(
  "does not grant collective consumption to %s from Swift permissions",
  async (role) => {
    memberships[1].roles = [role];
    h.legacyTeam = { id: "team-a", name: "Legacy", permissions: ["can_read", "can_update_resources"] };
    render();
    await until(() => expect(host.textContent).toContain("alice/Acme/usage"));
    expect(collectiveRequests()).toHaveLength(0);
    expect(host.textContent).not.toContain("rework.consumption.teamTitle");
    expect(host.textContent).toContain("rework.teamUsage.team.sectionTitle");
    expect(h.legacy.mock.calls.some(([, options]) => !(options as { skip: boolean }).skip)).toBe(true);
  },
);

it.each(["owner", "organization_admin"] as const)(
  "does not inherit %s authority from the organization",
  async (role) => {
    memberships = [space("Acme", "organization", [role])];
    render();
    await until(() => expect(host.textContent).toContain("alice/Acme/usage"));
    expect(collectiveRequests()).toHaveLength(0);
  },
);

it("does not turn a platform administrator into a collective reader", async () => {
  h.platformRoles = ["admin"];
  memberships[1].roles = ["member"];
  render();
  await until(() => expect(host.textContent).toContain("alice/Acme/usage"));
  expect(collectiveRequests()).toHaveLength(0);
  expect(host.textContent).not.toContain("rework.consumption.teamTitle");
});

it("uses the exact project scope and excludes personal and organization kinds", async () => {
  memberships.push(space("project-a", "project", ["analyst"]), space("personal-a", "personal", ["owner"]));
  render();
  await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
  hold = "project-a";
  act(() => navigate("/team/project-a/usage"));
  await until(() => expect(release).toBeDefined());
  expect(host.textContent).not.toContain("alice/team-a/usage");
  expect(host.textContent).toContain("common.loading");
  release!();
  await until(() => expect(host.textContent).toContain("alice/project-a/usage"));
  expect(host.textContent).toContain("rework.consumption.projectTitle");
  expect(host.textContent).toContain("rework.teamUsage.projectPageTitle");
  const collective = collectiveRequests();
  expect(
    collective[collective.length - 1].body.queries.every(
      (query) => query.scope.kind === "space" && query.scope.id === "project-a",
    ),
  ).toBe(true);
  act(() => navigate("/team/personal-a/usage"));
  await until(() => expect(host.textContent).toContain("rework.teamUsage.personalSkillsSectionTitle"));
  expect(host.textContent).not.toContain("alice/project-a/usage");
  act(() => navigate("/team/Acme/usage"));
  await flush();
  expect(collectiveRequests()).toHaveLength(2);
});

it.each(["missing", "error", "other-organization"])("skips consumption for %s context", async (kind) => {
  if (kind === "missing") memberships = [];
  if (kind === "error") membershipStatus = 503;
  if (kind === "other-organization") memberships[1].organization_id = "Globex";
  render();
  // Initial membership loading must not start any collective request either.
  expect(collectiveRequests()).toHaveLength(0);
  await until(() => expect(context.memberships.isFetching).toBe(false));
  await flush();
  expect(collectiveRequests()).toHaveLength(0);
  expect(host.textContent).not.toContain("rework.consumption.teamTitle");
});

it("hides revoked data on the existing authority focus refresh, including cached membership errors", async () => {
  render();
  await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
  memberships = [memberships[0], { ...memberships[1], roles: ["member"] }];
  act(() => window.dispatchEvent(new Event("focus")));
  await until(() => expect(host.textContent).not.toContain("alice/team-a/usage"));
  expect(host.textContent).not.toContain("rework.consumption.teamTitle");
  expect(collectiveRequests()).toHaveLength(1);
  memberships[1].roles = ["analyst"];
  act(() => window.dispatchEvent(new Event("focus")));
  await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
  membershipStatus = 503;
  act(() => window.dispatchEvent(new Event("focus")));
  await until(() => expect(host.textContent).not.toContain("alice/team-a/usage"));
});

it.each([403, 503])("hides cached consumption on a %i refresh failure and retains personal usage", async (status) => {
  render();
  await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
  click("fixed-period");
  await until(() => expect(collectiveRequests()).toHaveLength(2));
  await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
  collectiveStatus = status;
  click("common.refresh");
  await until(() => expect(collectiveRequests()).toHaveLength(3));
  await until(() => expect(host.textContent).toContain("common.loadingError"));
  expect(collectiveRequests()[2].body).toEqual(collectiveRequests()[1].body);
  expect(host.textContent).not.toContain("alice/team-a/usage");
  expect(host.textContent).toContain("alice/Acme/usage");
});

it("isolates period, account and organization changes with a late collective response", async () => {
  memberships.push(space("Globex", "organization", ["member"]), space("team-b", "team", ["owner"], "Globex"));
  render();
  await until(() => expect(host.textContent).toContain("alice/team-a/usage"));
  hold = "team-a";
  click("fixed-period");
  await until(() => expect(release).toBeDefined());
  expect(host.textContent).not.toContain("alice/team-a/usage");
  h.identity = "bob";
  render();
  await until(() => expect(host.textContent).toContain("bob/team-a/usage"));
  release!();
  await flush();
  expect(host.textContent).not.toContain("alice/team-a/usage");
  act(() => {
    context.selectOrganization("Globex");
  });
  await flush();
  expect(host.textContent).not.toContain("bob/team-a/usage");
  act(() => navigate("/team/team-b/usage"));
  await until(() => expect(host.textContent).toContain("bob/team-b/usage"));
  expect(host.textContent).not.toContain("bob/team-a/usage");
  expect(host.textContent).toContain("bob/Globex/usage");
});
