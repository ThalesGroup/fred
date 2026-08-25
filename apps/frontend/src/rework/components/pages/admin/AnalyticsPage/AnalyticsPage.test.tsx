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

// Focus: the admin-only section (storage_by_team, Activités, models-governance
// link — KPI-ANALYTICS-RFC.md §2.4/§2.5) must render only for a platform_admin
// (`useUserCapabilities().canAdmin`), never for a plain platform_observer —
// the frontend gate mirrors the backend's can_manage_platform check, it
// doesn't replace it, but a regression here would still leak the section's
// existence to every observer.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  capabilities: {
    canAdmin: false,
    canObservePlatform: true,
    canDebug: false,
    canEditSessions: true,
    canDeleteSessions: true,
    isLoading: false,
  },
  neutralQuery: () => ({ data: undefined, isLoading: false, isFetching: false, isError: false }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("react-router-dom", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}));

vi.mock("@hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => h.capabilities,
}));

// The real chart molecules call getComputedStyle at render time (PieChart) or
// pull in recharts/ResizeObserver machinery this Node-environment test suite
// has no DOM for — stub them to trivial title-echoing placeholders so this
// suite stays focused on AnalyticsPage's own section/gating logic, the same
// isolation CapabilitiesPage.test.tsx applies to its drawer.
vi.mock("@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/PieChart/PieChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/BarChart/BarChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/HistogramChart/HistogramChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/KpiStatCard/KpiStatCard", () => ({
  default: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@shared/molecules/TimeRangeSelector/TimeRangeSelector", () => ({
  default: () => <div data-testid="time-range-selector" />,
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useActiveUsersOverTimeQuery: h.neutralQuery,
  useUniqueUsersTotalQuery: h.neutralQuery,
  useSessionsOverTimeQuery: h.neutralQuery,
  useMessagesOverTimeQuery: h.neutralQuery,
  useSessionsByScopeQuery: h.neutralQuery,
  useConversationsPerUserQuery: h.neutralQuery,
  useConversationDepthQuery: h.neutralQuery,
  useTopTeamsBySessionsQuery: h.neutralQuery,
  useAgentsTotalQuery: h.neutralQuery,
  useDocumentsTotalQuery: h.neutralQuery,
  useTopAgentsByConversationsQuery: h.neutralQuery,
  useAgentPromptLengthDistributionQuery: h.neutralQuery,
  useTokenUsageOverTimeQuery: h.neutralQuery,
  useTokenUsageByAgentQuery: h.neutralQuery,
  useTokenUsageByModelQuery: h.neutralQuery,
  useStorageByTeamQuery: h.neutralQuery,
}));

import AnalyticsPage from "./AnalyticsPage";

function render(): string {
  return renderToStaticMarkup(<AnalyticsPage />);
}

describe("AnalyticsPage admin-only section (§2.4/§2.5)", () => {
  it("hides the administration section for a plain platform_observer", () => {
    h.capabilities = { ...h.capabilities, canAdmin: false };
    const html = render();
    expect(html).not.toContain("rework.analytics.sections.administration");
  });

  it("shows the administration section for a platform_admin", () => {
    h.capabilities = { ...h.capabilities, canAdmin: true };
    const html = render();
    expect(html).toContain("rework.analytics.sections.administration");
    expect(html).toContain("/admin/capabilities?kind=model");
  });

  it("renders the overview and token-usage sections regardless of role", () => {
    h.capabilities = { ...h.capabilities, canAdmin: false };
    const html = render();
    expect(html).toContain("rework.analytics.sections.overview");
    expect(html).toContain("rework.analytics.sections.tokenUsage");
  });

  // #2426: the engagement section is not admin-gated — it sits behind the same
  // can_observe_platform every non-admin section here requires.
  it("renders the engagement section for a plain platform_observer", () => {
    h.capabilities = { ...h.capabilities, canAdmin: false };
    const html = render();
    expect(html).toContain("rework.analytics.sections.engagement");
    expect(html).toContain("rework.analytics.engagement.conversationsPerUser.title");
    expect(html).toContain("rework.analytics.engagement.conversationDepth.title");
    expect(html).toContain("rework.analytics.engagement.conversationsPerUser.medianLabel");
    expect(html).toContain("rework.analytics.engagement.conversationDepth.medianLabel");
  });
});
