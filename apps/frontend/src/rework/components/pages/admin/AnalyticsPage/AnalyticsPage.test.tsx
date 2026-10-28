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
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";

function lookup(tree: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], tree);
}

const h = vi.hoisted(() => ({
  exportAnalytics: vi.fn(),
  showError: vi.fn(),
  neutralQuery: vi.fn(() => ({
    data: undefined,
    currentData: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  webResearchQuery: vi.fn((): { data: unknown; isLoading: boolean; isError: boolean } => ({
    data: { available: true, estimated_cost_eur: 1.5, searches: 10, by_reason: [] },
    isLoading: false,
    isError: false,
  })),
  skillQuery: vi.fn(() => ({
    data: undefined,
    currentData: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  overviewQuery: vi.fn(() => ({
    data: {
      visitors: { current: 80, previous: 40 },
      active_users: { current: 42, previous: 21 },
      active_teams: { current: 3, previous: 2 },
      conversations: { current: 30, previous: 30 },
      messages: { current: 120, previous: 100 },
      cost_eur: { current: 21, previous: 20 },
      cost_eur_per_active_user: { current: 0.5, previous: 0.95 },
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  adoptionQuery: vi.fn(() => ({
    data: {
      people_with_access: 200,
      visitors: { current: 80, previous: 40 },
      active_users: { current: 42, previous: 21 },
      visit_rate: { current: 0.4, previous: 0.2 },
      visitor_to_active_rate: { current: 0.525, previous: 0.525 },
      adoption_rate: { current: 0.21, previous: 0.105 },
      new_users: { current: 9, previous: 6 },
      next_month_return: { current: 0.64, previous: 0.6 },
      first_message_within_7_days_rate: { current: 0.71, previous: 0.7 },
      median_days_to_first_message: { current: 1, previous: 2 },
      cohorts: [
        { month: "2026-08", size: 38, returns: [0.62, 0.44, null] },
        { month: "2026-09", size: 0, returns: [null, null, null] },
        { month: "2026-10", size: 96, returns: [null, null, null] },
      ],
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  usageQuery: vi.fn(() => ({
    data: {
      active_users: { current: 42 },
      active_users_per_workday: { current: 12, previous: 10 },
      daily_usage_share: { current: 0.28, previous: 0.3 },
      conversations: { current: 30 },
      messages: { current: 120 },
      days_per_week_median: { current: 2.5 },
      conversations_per_user_median: { current: 3 },
      messages_per_conversation_median: { current: 4 },
      single_exchange_share: { current: 0.22, previous: 0.2 },
      top_decile_conversation_share: { current: 0.38 },
      conversation_distribution: [{ label: "1", value: 4 }],
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  activityQuery: vi.fn(() => ({
    data: { bucket: "week", series: [], points: [{ start: "2026-09-28", values: { messages: 5 } }] },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  teamsQuery: vi.fn(() => ({
    data: {
      active_teams: { current: 1, previous: 1 },
      team_share: { current: 0.6, previous: 0.5 },
      team_conversations: { current: 6 },
      personal_conversations: { current: 4 },
      rows: [{ team_id: "t-a", name: "Alpha", active_members: 1, messages: 9, messages_previous: 3 }],
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  agentsQuery: vi.fn(() => ({
    data: {
      agents_used: { current: 4, previous: 2 },
      agents_created: { current: 1 },
      agents_created_published: { current: 1, previous: 0 },
      documents_added: { current: 7 },
      teams_feeding_corpus: { current: 2 },
      corpus_searches: { current: 99 },
      top_agents: [{ agent_instance_id: "x", label: "Helper", users: 5, conversations: 6, messages: 9 }],
      capabilities: [
        { capability_id: "document_access", agents_equipped: 4, agents_used: 1, calls: 10, users: 3, failed_calls: 1 },
        { capability_id: "retired", agents_equipped: 0, agents_used: 1, calls: 2, users: 1, failed_calls: 0 },
      ],
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  qualityQuery: vi.fn(() => ({
    data: {
      failed_turn_rate: { current: 0.018, previous: 0.024 },
      cost_eur: { current: 21 },
      cost_eur_per_active_user: { current: 0.5 },
      input_tokens: { current: 1000 },
      output_tokens: { current: 100 },
      cached_input_tokens: { current: 0 },
      co2e_grams: { current: 500 },
      kwh: { current: 2 },
      models: [
        { model: "small", message_share: 1, input_tokens: 1000, output_tokens: 100, cost_eur: 21, co2e_grams: 500 },
      ],
      agents: [{ label: "__creation_assistant__", tokens: 10, cost_eur: 1, users: 0 }],
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  userFilterQuery: vi.fn((args: { userFilter?: string }) => ({
    currentData: args.userFilter
      ? { fields: [], known_users: 10, matched: 3, no_data: 2 }
      : { fields: [{ claim: ["organisation"], users: 8, in_rule: true }], known_users: 10 },
    isError: false,
  })),
  catalogQuery: vi.fn(() => ({
    data: {
      rows: [
        { team_id: "t-a", name: "Alpha", member_count: 2 },
        { team_id: "t-b", name: "Beta", member_count: 1 },
      ],
    },
  })),
}));

// Echoes the key, but honours defaultValue for keys the catalog does not have, like i18next.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue !== undefined && lookup(en, key) === undefined ? options.defaultValue : key,
    i18n: { language: "en" },
  }),
}));

vi.mock("react-router-dom", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}));

// Chart molecules need layout APIs this suite has no use for: title-echoing stubs.
vi.mock("@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart", () => ({
  default: ({
    title,
    series,
    barSeries,
    stacked,
  }: {
    title: string;
    series: string[];
    barSeries?: string[];
    stacked?: boolean;
  }) => (
    <div data-series={series.join(",")} data-bars={barSeries?.join(",")} data-stacked={stacked || undefined}>
      {title}
    </div>
  ),
}));
vi.mock("@shared/molecules/BarChart/BarChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/HistogramChart/HistogramChart", () => ({
  default: ({ title, emptyMessage }: { title: string; emptyMessage?: string }) => (
    <div>
      {title}
      {emptyMessage}
    </div>
  ),
}));
vi.mock("@shared/molecules/TimeRangeSelector/TimeRangeSelector", () => ({
  default: ({ presetKeys }: { presetKeys?: string[] }) => <div data-testid="time-range">{presetKeys?.join(",")}</div>,
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAnalyticsOverviewQuery: h.overviewQuery,
  useAnalyticsAdoptionQuery: h.adoptionQuery,
  useAnalyticsUsageQuery: h.usageQuery,
  useAnalyticsActivityOverTimeQuery: h.activityQuery,
  useAnalyticsTeamsQuery: h.teamsQuery,
  useAnalyticsAgentsQuery: h.agentsQuery,
  useAnalyticsQualityCostQuery: h.qualityQuery,
  useAgentsTotalQuery: h.neutralQuery,
  useSkillUsageQuery: h.skillQuery,
  useAgentPromptLengthDistributionQuery: h.neutralQuery,
  useCreationAssistantUsageQuery: h.neutralQuery,
  useStorageByTeamQuery: h.neutralQuery,
  useWebResearchSummaryQuery: h.webResearchQuery,
  useAnalyticsTeamsCatalogQuery: h.catalogQuery,
  useAnalyticsUserFilterQuery: h.userFilterQuery,
}));

vi.mock("./exportAnalytics", () => ({ exportAnalytics: h.exportAnalytics }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: h.showError, showInfo: vi.fn(), showSuccess: vi.fn() }),
}));

import AnalyticsPage from "./AnalyticsPage";
import AnalyticsView from "./AnalyticsView";
import { loadAnalyticsDays } from "./analyticsQuery";

// Weekends and French public holidays are left out until the viewer says otherwise.
const DEFAULT_DAYS_ARGS = { excludeWeekends: true, excludeHolidays: true };

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root | undefined;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<AnalyticsPage />));
}

const tabs = () => [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
const panel = () => container.querySelector('[role="tabpanel"]')?.textContent ?? "";

function openTab(id: string) {
  const tab = tabs().find((el) => el.textContent === `rework.analytics.tabs.${id}`)!;
  act(() => tab.click());
}

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  container.remove();
  vi.clearAllMocks();
});

// Section and tile keys each tab must show with today's presets.
const TAB_CONTENT: Record<string, string[]> = {
  overview: [
    "rework.analytics.tiles.activeUsers.label",
    "rework.analytics.tiles.newUsers.label",
    "rework.analytics.tiles.activeTeams.label",
    "rework.analytics.tiles.nextMonthReturn.label",
    "rework.analytics.tiles.conversations.label",
    "rework.analytics.tiles.messages.label",
    "rework.analytics.tiles.cost.label",
    "rework.analytics.charts.activityOverTime.title.week",
  ],
  adoption: [
    "rework.analytics.sections.reach.title",
    "rework.analytics.funnel.title",
    "rework.analytics.funnel.steps.peopleWithAccess.label",
    "rework.analytics.funnel.steps.visitors.label",
    "rework.analytics.funnel.steps.activeUsers.label",
    "rework.analytics.funnel.rates.visitRate.text",
    "rework.analytics.funnel.rates.visitorToActive.text",
    "rework.analytics.funnel.adoption.label",
    "rework.analytics.tiles.activeUsersPerWorkday.label",
    "rework.analytics.sections.activation.title",
    "rework.analytics.tiles.firstMessageWithin7Days.label",
    "rework.analytics.tiles.daysToFirstMessage.label",
    "rework.analytics.tables.cohorts.title",
    "rework.analytics.tables.cohorts.month",
  ],
  usage: [
    "rework.analytics.sections.volumes.title",
    "rework.analytics.sections.frequency.title",
    "rework.analytics.sections.distribution.title",
    "rework.analytics.tiles.daysPerWeek.label",
    "rework.analytics.tiles.conversationsPerUser.label",
    "rework.analytics.tiles.messagesPerConversation.label",
    "rework.analytics.tiles.dailyUsage.label",
    "rework.analytics.charts.messagesOverTime.title.week",
    "rework.analytics.charts.conversationDistribution.title",
    "rework.analytics.charts.conversationDistribution.topDecile.lead",
  ],
  teams: [
    "rework.analytics.sections.collective.title",
    "rework.analytics.sections.diffusion.title",
    "rework.analytics.conversationsByScope.shareChange",
    "rework.analytics.tables.teams.share",
  ],
  agents: [
    "rework.analytics.sections.agents.title",
    "rework.analytics.sections.capabilities.title",
    "rework.analytics.sections.skills.title",
    "rework.analytics.sections.knowledge.title",
    "rework.analytics.tiles.agentsUsed.label",
    "rework.analytics.tiles.agentsCreated.label",
    "rework.analytics.charts.topAgents.title",
    "rework.analytics.tables.capabilities.equipped",
    "rework.analytics.tiles.documentsAdded.label",
    "rework.analytics.tiles.teamsFeedingCorpus.label",
    "rework.analytics.tiles.corpusSearches.label",
  ],
  cost: [
    "rework.analytics.sections.quality.title",
    "rework.analytics.sections.cost.title",
    "rework.analytics.tiles.failedAnswers.label",
    "rework.analytics.tiles.singleExchange.label",
    "rework.analytics.tiles.tokens.label",
    "rework.analytics.tiles.footprint.label",
    "rework.analytics.charts.tokensOverTime.title.week",
    "rework.analytics.tables.models.title",
    "rework.analytics.tables.agentCost.title",
    "rework.analytics.tokenUsage.byAgent.creationAssistant",
  ],
  tech: [
    "rework.analytics.sections.webResearch.title",
    "rework.analytics.webResearch.searches",
    "rework.analytics.webResearch.fetches",
    "rework.analytics.webResearch.refused",
    "rework.analytics.webResearch.p95",
    "rework.analytics.sections.storage.title",
    "rework.analytics.tables.storage.empty",
    "rework.analytics.sections.agentBuild.title",
    "rework.analytics.tiles.creationAssistant.label",
    "rework.analytics.agents.promptLengthDistribution.title",
  ],
};

describe("AnalyticsPage", () => {
  it("renders the header controls and seven tabs, Overview first", () => {
    render();
    const text = container.textContent ?? "";
    expect(text).toContain("rework.analytics.title");
    expect(text).toContain("last3Months");
    expect(text).toContain("last12Months");
    const about = container.querySelector<HTMLElement>('[aria-label="rework.analytics.aboutLabel"]')!;
    expect(about.tagName).toBe("SPAN");
    expect(about.tabIndex).toBe(0);
    expect(tabs().map((el) => el.textContent)).toEqual(
      ["overview", "adoption", "usage", "teams", "agents", "cost", "tech"].map((id) => `rework.analytics.tabs.${id}`),
    );
    expect(tabs()[0].getAttribute("aria-selected")).toBe("true");
  });

  const exportButton = () =>
    [...container.querySelectorAll("button")].find((el) => el.textContent?.includes("rework.analytics.export"))!;

  it("exports the current period and scope, busy until the download is done", async () => {
    let finish!: () => void;
    h.exportAnalytics.mockReturnValueOnce(new Promise<void>((resolve) => (finish = resolve)));
    render();
    act(() => exportButton().click());

    expect(h.exportAnalytics).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        since: expect.any(String),
        until: expect.any(String),
        tz: expect.any(String),
        lang: "en",
      }),
    );
    expect(exportButton().disabled).toBe(true);
    expect(exportButton().textContent).toContain("rework.analytics.exporting");

    await act(async () => finish());
    expect(exportButton().disabled).toBe(false);
    expect(exportButton().textContent).not.toContain("exporting");
    expect(h.showError).not.toHaveBeenCalled();
  });

  it("says so in a toast when the export fails", async () => {
    h.exportAnalytics.mockRejectedValueOnce(new Error("HTTP 500"));
    render();
    await act(async () => exportButton().click());

    expect(h.showError).toHaveBeenCalledExactlyOnceWith({ summary: "rework.analytics.exportError" });
    expect(exportButton().disabled).toBe(false);
  });

  it("draws active users as bars under the visitors line", () => {
    render();
    const chart = container.querySelector<HTMLElement>("[data-series]")!;
    expect(chart.dataset.series).toBe(
      "rework.analytics.charts.activityOverTime.activeUsers,rework.analytics.charts.activityOverTime.visitors",
    );
    expect(chart.dataset.bars).toBe("rework.analytics.charts.activityOverTime.activeUsers");
  });

  it("stacks input and output tokens as bars, with the period totals under them", () => {
    render();
    openTab("cost");
    const chart = container.querySelector<HTMLElement>("[data-series]")!;
    expect(chart.dataset.bars).toBe(chart.dataset.series);
    expect(chart.dataset.stacked).toBe("true");
    expect(panel()).toContain("rework.analytics.charts.tokensOverTime.periodTotals");
  });

  it("splits team and personal conversations as one labelled bar", () => {
    render();
    openTab("teams");
    const bar = container.querySelector<HTMLElement>('[role="img"]')!;
    const segments = [...bar.children] as HTMLElement[];
    expect(segments.map((el) => el.style.width)).toEqual(["60%", "40%"]);
    expect(segments.map((el) => el.textContent)).toEqual([
      "rework.analytics.conversationsByScope.team · 60%",
      "rework.analytics.conversationsByScope.personal · 40%",
    ]);
    expect(bar.getAttribute("aria-label")).toContain("rework.analytics.conversationsByScope.team · 60%");
    expect(panel()).toContain("rework.analytics.conversationsByScope.teamCount");
    expect(panel()).toContain("rework.analytics.conversationsByScope.personalCount");
  });

  it.each(Object.entries(TAB_CONTENT))("shows the %s tab sections", (id, keys) => {
    render();
    openTab(id);
    expect(tabs().find((el) => el.getAttribute("aria-selected") === "true")?.textContent).toBe(
      `rework.analytics.tabs.${id}`,
    );
    for (const key of keys) {
      expect(panel()).toContain(key);
      expect(lookup(en, key), key).toBeTypeOf("string");
      expect(lookup(fr, key), key).toBeTypeOf("string");
    }
    // Info icons are plain focusable icons, never buttons.
    const panelEl = container.querySelector('[role="tabpanel"]')!;
    expect(panelEl.querySelector('button[aria-label^="rework.analytics.moreInfo"]')).toBeNull();
  });

  it("mounts only the selected tab, so other tabs' reads do not run", () => {
    render();
    expect(h.skillQuery).not.toHaveBeenCalled();
    openTab("tech");
    expect(panel()).not.toContain("rework.analytics.tiles.activeUsers.label");
    expect(h.skillQuery).not.toHaveBeenCalled();
    openTab("agents");
    expect(h.skillQuery).toHaveBeenCalledWith(
      { since: expect.any(String), until: expect.any(String), ...DEFAULT_DAYS_ARGS },
      { refetchOnMountOrArgChange: 300 },
    );
  });

  // Observers and admins read the same page; the backend alone decides what each preset returns.
  it("shows the Technical tab without any admin capability check", () => {
    render();
    openTab("tech");
    expect(panel()).toContain("rework.analytics.sections.storage.title");
  });

  it("shows a tile's value, caption and change against the previous period", () => {
    render();
    expect(panel()).toContain("42");
    expect(panel()).toContain("rework.analytics.tiles.activeUsers.caption");
    expect(panel()).toContain("rework.analytics.delta.relative");
    expect(panel()).toContain("rework.analytics.tiles.activeTeams.caption");
  });

  it("shows the web research cost in euros, and nothing while web research is disabled", () => {
    render();
    openTab("tech");
    expect(panel()).toContain("rework.analytics.sections.webResearch.title");
    expect(panel()).toContain("€1.50");
    act(() => root?.unmount());
    container.remove();

    const previous = h.webResearchQuery.getMockImplementation()!;
    h.webResearchQuery.mockReturnValue({ data: { available: false }, isLoading: false, isError: false });
    try {
      render();
      openTab("tech");
      expect(panel()).not.toContain("rework.analytics.sections.webResearch.title");
      expect(panel()).not.toContain("rework.analytics.webResearch.");
    } finally {
      h.webResearchQuery.mockImplementation(previous);
    }
  });

  it("draws the adoption funnel with its step rates and changes", () => {
    render();
    openTab("adoption");
    const bars = [...container.querySelectorAll('[role="progressbar"]')].map((el) => el.getAttribute("aria-valuenow"));
    // Bars are relative to the widest step, people with access.
    expect(bars).toEqual(["100", "40", "21"]);
    expect(panel()).toContain("200");
    expect(panel()).toContain("40%");
    expect(panel()).toContain("52.5%");
    expect(panel()).toContain("21%");
    expect(panel()).toContain("rework.analytics.delta.points");
  });

  it("shades cohort cells by return share and marks months still to come", () => {
    render();
    openTab("adoption");
    const table = container.querySelector("table")!;
    const header = [...table.querySelectorAll("thead th")].map((el) => el.textContent);
    expect(header).toEqual([
      "rework.analytics.tables.cohorts.month",
      "rework.analytics.tables.cohorts.size",
      ...[1, 2, 3].map(() => "rework.analytics.tables.cohorts.monthPlus"),
    ]);
    const rows = [...table.querySelectorAll("tbody tr")];
    expect(rows.map((r) => r.querySelector("th")?.textContent)).toEqual([
      "August 2026",
      "September 2026",
      "October 2026",
    ]);
    const august = [...rows[0].querySelectorAll("td")];
    expect(august.map((c) => c.textContent)).toEqual(["38", "62%", "44%", "—"]);
    expect(august.slice(1).map((c) => c.getAttribute("data-level"))).toEqual(["high", "fair", "none"]);
    expect(panel()).toContain("1 day");
  });

  it("shows new users and next-month return on the Overview from the adoption read", () => {
    render();
    expect(panel()).toContain("rework.analytics.tiles.newUsers.caption");
    expect(panel()).toContain("64%");
    expect(h.adoptionQuery).toHaveBeenCalledWith(
      { since: expect.any(String), until: expect.any(String), tz: expect.any(String), ...DEFAULT_DAYS_ARGS },
      { refetchOnMountOrArgChange: 300 },
    );
  });

  it("says when people with access are unknown", () => {
    h.adoptionQuery.mockReturnValue({
      data: {
        people_with_access: null,
        visitors: { current: 8 },
        active_users: { current: 4 },
        visit_rate: {},
        visitor_to_active_rate: { current: 0.5 },
        adoption_rate: {},
        new_users: {},
        next_month_return: {},
        first_message_within_7_days_rate: {},
        median_days_to_first_message: {},
        cohorts: [],
      },
      isLoading: false,
      isFetching: false,
      isError: false,
    } as never);
    render();
    openTab("adoption");
    expect(panel()).toContain("rework.analytics.funnel.unknown");
    expect(panel()).not.toContain("rework.analytics.funnel.rates.visitRate.text");
    h.adoptionQuery.mockReset();
  });

  it("shows capability use: rate over equipped agents and failed share of calls", () => {
    render();
    openTab("agents");
    // document_access: 1 of 4 equipped agents used it, 1 of 10 calls failed.
    expect(panel()).toContain("25%");
    expect(panel()).toContain("10%");
    for (const key of ["used", "usageRate", "calls", "users", "failed"]) {
      expect(panel()).toContain(`rework.analytics.tables.capabilities.${key}`);
    }
  });

  it("ranks the top agents and flags a capability mostly turned on for nothing", () => {
    render();
    openTab("agents");
    const panelEl = container.querySelector('[role="tabpanel"]')!;
    expect(panelEl.querySelector('[role="progressbar"][aria-label="Helper"]')).not.toBeNull();
    expect(panel()).toContain(
      "rework.analytics.charts.topAgents.conversations · rework.analytics.charts.topAgents.users",
    );
    const rate = [...panelEl.querySelectorAll("[data-tone]")].find((el) => el.textContent === "25%");
    expect(rate?.getAttribute("data-tone")).toBe("warning");
  });

  it("marks a team's change with a direction glyph and draws its active share", () => {
    render();
    openTab("teams");
    expect(panel()).toContain("▲ +200%");
    expect(container.querySelector('[role="tabpanel"] [role="progressbar"][aria-label="50%"]')).not.toBeNull();
  });

  it("sums up web research in six tiles, refusals together and p95 in seconds", () => {
    h.webResearchQuery.mockReturnValueOnce({
      data: {
        available: true,
        tool_calls: 200,
        searches: 40,
        fetches: 124,
        estimated_cost_eur: 1.5,
        blocked: 3,
        saturated: 2,
        failed: 5,
        unique_users: 9,
        p95_ms: 4800,
        by_reason: [{ label: "busy", value: 2 }],
      },
      isLoading: false,
      isError: false,
    });
    render();
    openTab("tech");
    const tiles = [...container.querySelectorAll('[role="tabpanel"] section[data-nested]')].filter((el) =>
      el.textContent?.startsWith("rework.analytics.webResearch."),
    );
    expect(tiles).toHaveLength(6);
    expect(panel()).toContain("3 / 2 / 5");
    expect(panel()).toContain("rework.analytics.webResearch.shareOfCalls");
    expect(panel()).toContain("rework.analytics.webResearch.pagesPerSearch");
    expect(panel()).toContain("4.8 sec");
    expect(panel()).not.toContain("4800");
  });

  it("lists storage per team with used space, quota and a warning from 80%", () => {
    h.neutralQuery.mockImplementation(() => ({
      data: {
        rows: [
          { team_id: "a", label: "Small", used_bytes: 1024, quota_bytes: 10240 },
          { team_id: "b", label: "Full", used_bytes: 9216, quota_bytes: 10240 },
          { team_id: "c", label: "Unbounded", used_bytes: 2048, quota_bytes: null },
        ],
      },
      currentData: undefined,
      isLoading: false,
      isFetching: false,
      isError: false,
    }));
    try {
      render();
      openTab("tech");
      const text = panel();
      expect(text.indexOf("Full")).toBeLessThan(text.indexOf("Small"));
      expect(text.indexOf("Small")).toBeLessThan(text.indexOf("Unbounded"));
      const full = [...container.querySelectorAll("[data-tone]")].find((el) => el.textContent === "90%");
      expect(full?.getAttribute("data-tone")).toBe("warning");
      expect(text).toContain("10%");
    } finally {
      h.neutralQuery.mockReset();
      h.neutralQuery.mockImplementation(() => ({
        data: undefined,
        currentData: undefined,
        isLoading: false,
        isFetching: false,
        isError: false,
      }));
    }
  });

  it("captions created agents with the published ones", () => {
    render();
    openTab("agents");
    expect(panel()).toContain("rework.analytics.tiles.agentsCreated.published");
    expect(lookup(en, "rework.analytics.tiles.agentsCreated.published_other")).toBeTypeOf("string");
  });

  it("falls back to the service notice when every read of a tab fails", () => {
    const failed = { data: undefined, isLoading: false, isFetching: false, isError: true } as never;
    h.adoptionQuery.mockReturnValue(failed);
    h.usageQuery.mockReturnValue(failed);
    render();
    openTab("adoption");
    expect(panel()).toContain("rework.serviceNotice.controlPlane.title");
    h.adoptionQuery.mockReset();
    h.usageQuery.mockReset();
  });

  it("hides a previous range's skill rows while the current request is fetching", () => {
    h.skillQuery.mockReturnValue({
      data: { rows: [{ skill_name: "stale-skill", user_count: 9, model_count: 1, total: 10 }] },
      currentData: undefined,
      isLoading: false,
      isFetching: true,
      isError: false,
    } as never);
    render();
    openTab("agents");
    expect(panel()).not.toContain("stale-skill");
    expect(panel()).toContain("common.loading");
    h.skillQuery.mockReset();
    h.skillQuery.mockImplementation(() => ({
      data: undefined,
      currentData: undefined,
      isLoading: false,
      isFetching: false,
      isError: false,
    }));
  });
});

describe("AnalyticsPage team scope", () => {
  function selectTeams(...names: string[]) {
    const trigger = container.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!;
    act(() => trigger.click());
    for (const name of names) {
      const row = [...container.querySelectorAll("label")].find((el) => el.textContent?.includes(name))!;
      act(() => row.querySelector("input")!.click());
    }
    const apply = [...container.querySelectorAll("button")].find(
      (el) => el.textContent === "rework.analytics.scope.apply",
    )!;
    act(() => apply.click());
  }

  it("passes the applied teams to every scoped read", () => {
    render();
    openTab("agents");
    selectTeams("Beta", "Alpha");
    expect(h.skillQuery).toHaveBeenLastCalledWith(
      { since: expect.any(String), until: expect.any(String), teamIds: ["t-a", "t-b"], ...DEFAULT_DAYS_ARGS },
      { refetchOnMountOrArgChange: 300 },
    );
    expect(container.textContent).toContain("rework.analytics.scope.membersTotal");
    expect(h.agentsQuery).toHaveBeenLastCalledWith(
      { since: expect.any(String), until: expect.any(String), teamIds: ["t-a", "t-b"], ...DEFAULT_DAYS_ARGS },
      { refetchOnMountOrArgChange: 300 },
    );
    expect(panel()).toContain("rework.analytics.scope.notForTeamsShort");
  });

  it("exports the applied teams", async () => {
    h.exportAnalytics.mockResolvedValueOnce(undefined);
    render();
    selectTeams("Alpha");
    const button = [...container.querySelectorAll("button")].find((el) =>
      el.textContent?.includes("rework.analytics.export"),
    )!;
    await act(async () => button.click());
    expect(h.exportAnalytics).toHaveBeenCalledWith(expect.objectContaining({ teamIds: ["t-a"] }));
  });

  describe("counted days", () => {
    const exportButton = () =>
      [...container.querySelectorAll("button")].find((el) => el.textContent?.includes("rework.analytics.export"))!;
    const settingsButton = () =>
      container.querySelector<HTMLButtonElement>('button[aria-label="rework.analytics.days.open"]')!;
    const switchFor = (key: string) => {
      const label = [...document.querySelectorAll("span")].find((el) => el.textContent === key)!;
      return document.querySelector<HTMLInputElement>(`input[aria-labelledby="${label.id}"]`)!;
    };

    afterEach(() => localStorage.clear());

    it("leaves weekends and holidays out of every activity read and the export by default", async () => {
      render();
      for (const query of [h.overviewQuery, h.activityQuery, h.adoptionQuery]) {
        expect(query).toHaveBeenCalledWith(expect.objectContaining(DEFAULT_DAYS_ARGS), expect.anything());
      }
      await act(async () => exportButton().click());
      expect(h.exportAnalytics).toHaveBeenCalledWith(expect.objectContaining(DEFAULT_DAYS_ARGS));
    });

    it("applies a switch at once and remembers it for the viewer", () => {
      render();
      act(() => settingsButton().click());
      const weekends = switchFor("rework.analytics.days.excludeWeekends");
      expect(weekends.checked).toBe(true);
      expect(switchFor("rework.analytics.days.excludeHolidays").checked).toBe(true);
      vi.clearAllMocks();
      act(() => weekends.click());
      expect(h.overviewQuery).toHaveBeenCalledWith(
        expect.objectContaining({ excludeWeekends: false, excludeHolidays: true }),
        expect.anything(),
      );
      expect(JSON.parse(localStorage.getItem("analytics.days")!)).toEqual({
        excludeWeekends: false,
        excludeHolidays: true,
      });

      act(() => root?.unmount());
      container.remove();
      vi.clearAllMocks();
      render();
      expect(h.overviewQuery).toHaveBeenCalledWith(
        expect.objectContaining({ excludeWeekends: false }),
        expect.anything(),
      );
    });

    it("falls back to the defaults when storage is unreadable", () => {
      localStorage.setItem("analytics.days", "{not json");
      expect(loadAnalyticsDays()).toEqual({ excludeWeekends: true, excludeHolidays: true });
      const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new Error("blocked");
      });
      expect(loadAnalyticsDays()).toEqual({ excludeWeekends: true, excludeHolidays: true });
      getItem.mockRestore();
    });
  });

  it("sends the viewer's time zone with calendar reads", () => {
    render();
    expect(h.activityQuery).toHaveBeenCalledWith(
      { since: expect.any(String), until: expect.any(String), tz: expect.any(String), ...DEFAULT_DAYS_ARGS },
      { refetchOnMountOrArgChange: 300 },
    );
  });

  it("skips reads without team data under a team scope and says so", () => {
    render();
    openTab("tech");
    selectTeams("Alpha");
    expect(h.neutralQuery).toHaveBeenCalledWith(
      { since: expect.any(String), until: expect.any(String), teamIds: ["t-a"] },
      { refetchOnMountOrArgChange: 300, skip: true },
    );
    expect(panel()).toContain("rework.analytics.scope.notForTeams");
    // The creation assistant tile states it too, not a blank card.
    expect(panel()).toContain("rework.analytics.scope.notForTeamsShort");
  });
});

describe("AnalyticsPage user filter", () => {
  const FILTER = JSON.stringify({
    combination: "all",
    conditions: [{ claim: ["organisation"], operator: "equals", value: "Acme", case_sensitive: false }],
  });
  const button = (text: string) =>
    [...container.querySelectorAll("button")].find((el) => el.textContent?.includes(text))!;

  function applyFilter() {
    act(() => button("rework.analytics.userFilter.title").click());
    act(() => button("rework.platformAccess.rule.addCondition").click());
    // The field list shows the stored paths with how many users have a value.
    expect(container.textContent).toContain("rework.analytics.userFilter.fieldUsers");
    act(() => button("organisation").click());
    const value = container.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.rule.value"]')!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(value, "Acme");
      value.dispatchEvent(new Event("input", { bubbles: true }));
    });
    act(() => vi.advanceTimersByTime(500));
    // Coverage of the draft before applying it.
    expect(h.userFilterQuery).toHaveBeenCalledWith({ userFilter: FILTER }, expect.objectContaining({ skip: false }));
    expect(container.textContent).toContain("rework.analytics.userFilter.matched");
    expect(container.textContent).toContain("rework.analytics.userFilter.noData");
    act(() => button("rework.analytics.scope.apply").click());
  }

  afterEach(() => vi.useRealTimers());

  it("restricts every user-based read and the export to the applied filter", async () => {
    vi.useFakeTimers();
    render();
    openTab("agents");
    applyFilter();
    expect(h.agentsQuery).toHaveBeenLastCalledWith(
      { since: expect.any(String), until: expect.any(String), userFilter: FILTER, ...DEFAULT_DAYS_ARGS },
      { refetchOnMountOrArgChange: 300 },
    );
    expect(h.skillQuery).toHaveBeenLastCalledWith(expect.objectContaining({ userFilter: FILTER }), expect.anything());
    // Agents existing are configuration: read without the filter.
    expect(h.neutralQuery).toHaveBeenLastCalledWith(
      { since: expect.any(String), until: expect.any(String) },
      expect.anything(),
    );
    // The summary names the filter, its coverage and what stays unfiltered.
    expect(container.textContent).toContain("rework.analytics.userFilter.condition");
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.textContent).toContain("rework.analytics.userFilter.matched");
    h.exportAnalytics.mockResolvedValueOnce(undefined);
    await act(async () => button("rework.analytics.export").click());
    expect(h.exportAnalytics).toHaveBeenCalledWith(expect.objectContaining({ userFilter: FILTER }));
  });

  it("clears the filter from the summary chip", () => {
    vi.useFakeTimers();
    render();
    applyFilter();
    const remove = container.querySelector<HTMLButtonElement>(
      'button[aria-label="rework.analytics.userFilter.clear"]',
    )!;
    act(() => remove.click());
    expect(h.overviewQuery).toHaveBeenLastCalledWith(
      { since: expect.any(String), until: expect.any(String), ...DEFAULT_DAYS_ARGS },
      expect.anything(),
    );
    expect(container.textContent).not.toContain("rework.analytics.userFilter.condition");
  });

  it("is not offered on a team's page", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root!.render(<AnalyticsView title="Team" mode="team" teamIds={["t-a"]} />));
    expect(container.textContent).not.toContain("rework.analytics.userFilter.title");
    expect(h.userFilterQuery).not.toHaveBeenCalled();
  });
});

describe("analytics catalog", () => {
  const keysOf = (node: unknown, prefix = ""): string[] =>
    typeof node === "object" && node !== null
      ? Object.entries(node).flatMap(([k, v]) => keysOf(v, prefix ? `${prefix}.${k}` : k))
      : [prefix];

  it("has the same keys in French and English", () => {
    expect(keysOf(lookup(fr, "rework.analytics")).sort()).toEqual(keysOf(lookup(en, "rework.analytics")).sort());
  });

  it("never names the platform in its copy", () => {
    for (const catalog of [en, fr]) {
      expect(JSON.stringify(lookup(catalog, "rework.analytics"))).not.toMatch(/\bFred\b/);
    }
  });
});
