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

// Focus: the new team sections (KPI-ANALYTICS-RFC.md §2.5 Page 2) are
// capability-conditional, in-page gating with no route guard
// (FRONTEND-AUTHZ-PATTERN.md). `useTeamCapabilities`/`hasElevatedTeamRole`
// run for real here (pure functions over `TeamPermission[]`) so each test
// only has to set the permission array a real backend would return for that
// role, rather than hand-picking booleans that could drift from the mapping.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TeamPermission, TeamWithPermissions } from "../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  selected: {
    teamId: "team-1",
    selectedTeam: undefined as TeamWithPermissions | undefined,
  },
  neutralQuery: () => ({ data: undefined, isLoading: false, isFetching: false, isError: false }),
}));

function team(permissions: TeamPermission[]): TeamWithPermissions {
  return { id: "team-1", name: "Team One", member_count: 4, permissions };
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => h.selected,
}));

vi.mock("@shared/organisms/TaskActivity/TaskActivity.tsx", () => ({
  default: ({ scope, teamId, kind }: { scope: string; teamId?: string; kind?: string }) => (
    <div data-testid={`task-activity-${scope}-${kind ?? "all"}-${teamId}`} />
  ),
}));

vi.mock("@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/BarChart/BarChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/KpiStatCard/KpiStatCard", () => ({
  default: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@shared/molecules/TimeRangeSelector/TimeRangeSelector", () => ({
  default: () => <div data-testid="time-range-selector" />,
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useUserTokenUsageOverTimeQuery: h.neutralQuery,
  useUserTokenUsageByAgentQuery: h.neutralQuery,
  useUserTokenUsageByModelQuery: h.neutralQuery,
  useAgentsTotalQuery: h.neutralQuery,
  useDocumentsTotalQuery: h.neutralQuery,
  useSessionsOverTimeQuery: h.neutralQuery,
  useStorageByTeamQuery: h.neutralQuery,
  useTeamActivitySummaryQuery: h.neutralQuery,
  useTokenUsageOverTimeQuery: h.neutralQuery,
  useTokenUsageByAgentQuery: h.neutralQuery,
  useTokenUsageByModelQuery: h.neutralQuery,
  useTopAgentsByConversationsQuery: h.neutralQuery,
}));

import TeamUsagePage from "./TeamUsagePage";

function render(): string {
  return renderToStaticMarkup(<TeamUsagePage />);
}

describe("TeamUsagePage capability-conditional sections (§2.5 Page 2)", () => {
  it("shows only the personal section for a plain team_member (no elevated role)", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_use_team_agents"]) };
    const html = render();
    expect(html).toContain("rework.teamUsage.personalSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.sectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.editorSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.adminSectionTitle");
  });

  it("shows only the personal section on a personal team (no team context at all)", () => {
    h.selected = { teamId: "personal-u1", selectedTeam: undefined };
    const html = render();
    expect(html).toContain("rework.teamUsage.personalSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.sectionTitle");
  });

  it("shows the shared team section for team_analyst (can_run_evaluations), not the editor/admin sections", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_run_evaluations"]) };
    const html = render();
    expect(html).toContain("rework.teamUsage.team.sectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.editorSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.adminSectionTitle");
  });

  it("shows the shared + editor sections for team_editor (can_update_resources), not the admin section", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_update_resources", "can_update_agents"]) };
    const html = render();
    expect(html).toContain("rework.teamUsage.team.sectionTitle");
    expect(html).toContain("rework.teamUsage.team.editorSectionTitle");
    expect(html).toContain("task-activity-team-ingestion-team-1");
    expect(html).not.toContain("rework.teamUsage.team.adminSectionTitle");
  });

  it("shows the shared + admin sections for team_admin (can_update_info), not the editor section", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_update_info"]) };
    const html = render();
    expect(html).toContain("rework.teamUsage.team.sectionTitle");
    expect(html).toContain("rework.teamUsage.team.adminSectionTitle");
    expect(html).toContain("task-activity-team-all-team-1");
    expect(html).not.toContain("rework.teamUsage.team.editorSectionTitle");
  });
});
