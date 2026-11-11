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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import type { TeamPermission, TeamWithPermissions } from "../../../../slices/controlPlane/controlPlaneOpenApi";

const query = (data?: unknown) => ({ data, currentData: data, isLoading: false, isFetching: false, isError: false });

const h = vi.hoisted(() => ({
  selected: { teamId: "team-1", selectedTeam: undefined as unknown, isPersonalTeam: false },
  exportAnalytics: vi.fn(),
  hooks: {} as Record<string, Mock<(...args: unknown[]) => unknown>>,
}));

function hook(name: string, data?: unknown) {
  h.hooks[name] ??= vi.fn(() => query(data));
  return h.hooks[name];
}

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => {
  const names = [
    "useAnalyticsOverviewQuery",
    "useAnalyticsAdoptionQuery",
    "useAnalyticsUsageQuery",
    "useAnalyticsActivityOverTimeQuery",
    "useAnalyticsAgentsQuery",
    "useAnalyticsQualityCostQuery",
    "useAnalyticsTeamsCatalogQuery",
    "useAgentsTotalQuery",
    "useSkillUsageQuery",
    "useUserSkillUsageQuery",
    "useUserTokenUsageByAgentQuery",
    "useUserTokenUsageByModelQuery",
  ];
  return {
    ...Object.fromEntries(names.map((n) => [n, (...args: unknown[]) => hook(n)(...args)])),
    useAnalyticsTeamsQuery: (...args: unknown[]) =>
      hook("useAnalyticsTeamsQuery", {
        active_teams: { current: 1, previous: 1 },
        rows: [{ team_id: "team-1", name: "Team One", active_members: 3, messages: 9, messages_previous: 3 }],
      })(...args),
    useUserTokenUsageOverTimeQuery: (...args: unknown[]) =>
      hook("useUserTokenUsageOverTimeQuery", {
        rows: [{ date: "Oct 1", value: 10, co2e_grams: 1, kwh: 0.1, cost_eur: 0.0123 }],
        interval: "1d",
      })(...args),
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { cost?: string }) => (options?.cost ? `${key}:${options.cost}` : key),
    i18n: { language: "fr" },
  }),
}));
vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({ useSelectedTeam: () => h.selected }));
vi.mock("../admin/AnalyticsPage/exportAnalytics", () => ({ exportAnalytics: h.exportAnalytics }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showInfo: vi.fn(), showSuccess: vi.fn() }),
}));
for (const chart of ["TimeSeriesLineChart", "MultiSeriesLineChart", "BarChart", "HistogramChart"]) {
  vi.doMock(`@shared/molecules/${chart}/${chart}`, () => ({
    default: ({ title }: { title: string }) => <div>{title}</div>,
  }));
}
vi.mock("@shared/molecules/TimeRangeSelector/TimeRangeSelector", () => ({
  default: () => <div data-testid="time-range" />,
}));

const { default: TeamUsagePage } = await import("./TeamUsagePage");

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root | undefined;

function team(permissions: TeamPermission[]): TeamWithPermissions {
  return { id: "team-1", name: "Team One", member_count: 4, permissions };
}

function render(selected: typeof h.selected) {
  h.selected = selected;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<TeamUsagePage />));
}

const asAdmin = () =>
  render({ teamId: "team-1", selectedTeam: team(["can_read", "can_read_analytics"]), isPersonalTeam: false });
const tabs = () => [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
const panel = () => container.querySelector('[role="tabpanel"]')?.textContent ?? "";
const button = (text: string) =>
  [...container.querySelectorAll("button")].find((el) => el.textContent?.includes(text))!;
function openTab(label: string) {
  act(() =>
    tabs()
      .find((el) => el.textContent === label)!
      .click(),
  );
}
const analyticsHooks = () => Object.keys(h.hooks).filter((n) => /Analytics|AgentsTotal|useSkillUsage/.test(n));

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  container.remove();
  Object.values(h.hooks).forEach((fn) => fn.mockClear());
  vi.clearAllMocks();
});

describe("TeamUsagePage for a team admin", () => {
  it("shows the analytics tabs without Technical, then the personal tab, and no scope selector", () => {
    asAdmin();
    expect(container.textContent).toContain("rework.analytics.title");
    expect(tabs().map((el) => el.textContent)).toEqual([
      ...["overview", "adoption", "usage", "teams", "agents", "cost"].map((id) => `rework.analytics.tabs.${id}`),
      "rework.teamUsage.personalSectionTitle",
    ]);
    // The counted days settings is the only dialog the team page offers.
    expect(
      container.querySelector('button[aria-haspopup="dialog"]:not([aria-label="rework.analytics.days.open"])'),
    ).toBeNull();
    expect(container.querySelector('[aria-label="rework.analytics.aboutLabel"]')).not.toBeNull();
  });

  it("scopes every read to the team and never reads the platform team catalog", () => {
    asAdmin();
    expect(h.hooks.useAnalyticsOverviewQuery).toHaveBeenCalledWith(
      {
        since: expect.any(String),
        until: expect.any(String),
        teamIds: ["team-1"],
        excludeWeekends: true,
        excludeHolidays: true,
      },
      { refetchOnMountOrArgChange: 300 },
    );
    expect(h.hooks.useAnalyticsTeamsCatalogQuery).toHaveBeenCalledWith({}, expect.objectContaining({ skip: true }));
    expect(panel()).not.toContain("rework.analytics.tiles.activeTeams.label");
    openTab("rework.analytics.tabs.teams");
    expect(h.hooks.useAnalyticsTeamsCatalogQuery).toHaveBeenLastCalledWith(
      { teamIds: ["team-1"] },
      { refetchOnMountOrArgChange: 300 },
    );
  });

  it("shows the team's own members on the Teams tab, without cross-team figures", () => {
    asAdmin();
    openTab("rework.analytics.tabs.teams");
    expect(panel()).toContain("rework.analytics.sections.members.title");
    expect(panel()).toContain("rework.analytics.tables.teams.active");
    expect(panel()).not.toContain("rework.analytics.tiles.teamShare.label");
    expect(panel()).not.toContain("rework.analytics.tables.teams.title");
    expect(panel()).not.toContain("rework.analytics.conversationsByScope.title");
  });

  it("hides the corpus figures that only exist across teams", () => {
    asAdmin();
    openTab("rework.analytics.tabs.agents");
    expect(panel()).toContain("rework.analytics.tiles.documentsAdded.label");
    expect(panel()).not.toContain("rework.analytics.tiles.teamsFeedingCorpus.label");
    expect(panel()).not.toContain("rework.analytics.tiles.corpusSearches.label");
  });

  it("exports the team only", async () => {
    h.exportAnalytics.mockResolvedValueOnce(undefined);
    asAdmin();
    await act(async () => button("rework.analytics.export").click());
    expect(h.exportAnalytics).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ teamIds: ["team-1"], lang: "fr" }),
    );
  });

  it("shows the viewer's own usage on the personal tab, cost in euros", () => {
    asAdmin();
    openTab("rework.teamUsage.personalSectionTitle");
    expect(panel()).toContain("rework.teamUsage.tokensOverTime.title");
    act(() => button("rework.tokenUsageImpact.costTitle").click());
    expect(panel()).toMatch(/rework\.tokenUsageImpact\.costValue:0,0123\s€/);
    expect(h.hooks.useUserTokenUsageOverTimeQuery).toHaveBeenCalledWith(
      { since: expect.any(String), until: expect.any(String) },
      { refetchOnMountOrArgChange: 300 },
    );
  });
});

describe("TeamUsagePage for everyone else", () => {
  it("shows a member without team admin rights their own usage only, with no team read", () => {
    render({ teamId: "team-1", selectedTeam: team(["can_read", "can_read_members"]), isPersonalTeam: false });
    expect(container.textContent).toContain("rework.teamUsage.title");
    expect(container.textContent).toContain("rework.teamUsage.personalSectionTitle");
    expect(tabs()).toHaveLength(0);
    expect(container.textContent).not.toContain("rework.analytics.export");
    expect(analyticsHooks().filter((n) => h.hooks[n].mock.calls.length > 0)).toEqual([]);
    expect(h.hooks.useUserSkillUsageQuery).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ skip: true }),
    );
  });

  it("shows the personal skill loads in a personal space", () => {
    render({ teamId: "personal-u1", selectedTeam: undefined, isPersonalTeam: true });
    expect(container.textContent).toContain("rework.teamUsage.personalSkillsSectionTitle");
    expect(tabs()).toHaveLength(0);
    expect(h.hooks.useUserSkillUsageQuery).toHaveBeenCalledWith(
      { since: expect.any(String), until: expect.any(String) },
      { refetchOnMountOrArgChange: 300, skip: false },
    );
  });
});
