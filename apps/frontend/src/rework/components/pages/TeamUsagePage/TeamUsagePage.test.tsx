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
    isPersonalTeam: false,
  },
  skillQuery: vi.fn(() => ({
    data: undefined,
    currentData: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  personalSkillQuery: vi.fn(() => ({
    currentData: undefined,
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
  })),
  neutralQuery: vi.fn(() => ({ data: undefined, isLoading: false, isFetching: false, isError: false })),
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

vi.mock("@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/BarChart/BarChart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("@shared/molecules/KpiStatCard/LocalizedKpiStatCard", () => ({
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
  useSkillUsageQuery: h.skillQuery,
  useUserSkillUsageQuery: h.personalSkillQuery,
  useDocumentsTotalQuery: h.neutralQuery,
  useSessionsOverTimeQuery: h.neutralQuery,
  useStorageByTeamQuery: h.neutralQuery,
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
  it("shows only the personal section and the personal title for a plain team_member (no elevated role)", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_use_team_agents"]), isPersonalTeam: false };
    const html = render();
    expect(html).toContain("rework.teamUsage.title");
    expect(html).not.toContain("rework.teamUsage.team.pageTitle");
    expect(html).toContain("rework.teamUsage.personalSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.sectionTitle");
    expect(h.skillQuery).toHaveBeenLastCalledWith(expect.objectContaining({ teamId: h.selected.teamId }), {
      skip: true,
      refetchOnMountOrArgChange: 300,
    });
  });

  it("shows only the personal section on a personal team (no team context at all)", () => {
    h.selected = { teamId: "personal-u1", selectedTeam: undefined, isPersonalTeam: true };
    const html = render();
    expect(html).toContain("rework.teamUsage.title");
    expect(html).toContain("rework.teamUsage.personalSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.sectionTitle");
  });

  it("shows only the personal section on a personal team even though the backend grants it team_editor-shaped permissions (build_personal_team)", () => {
    // Regression: `teams/system.py::build_personal_team` unconditionally grants
    // can_update_resources/can_update_agents so the owner can manage their own
    // docs/agents — that's a personal-resource permission, not an elevated
    // *team* role, and must not unlock the collaborative-team sections.
    h.selected = {
      teamId: "personal-u1",
      selectedTeam: team(["can_read", "can_update_resources", "can_update_agents"]),
      isPersonalTeam: true,
    };
    const html = render();
    expect(html).toContain("rework.teamUsage.title");
    expect(html).toContain("rework.teamUsage.personalSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.sectionTitle");
  });

  it("shows the shared team section and the team title for team_analyst (can_run_evaluations)", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_run_evaluations"]), isPersonalTeam: false };
    const html = render();
    expect(html).toContain("rework.teamUsage.team.pageTitle");
    expect(html).toContain("rework.analytics.skillUsage.title");
    expect(h.skillQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({ teamId: "team-1", since: expect.any(String), until: expect.any(String) }),
      { skip: false, refetchOnMountOrArgChange: 300 },
    );
    expect(html).not.toContain("rework.teamUsage.title");
    expect(html).toContain("rework.teamUsage.team.sectionTitle");
  });

  it("shows the shared team section and the team title for team_editor (can_update_resources)", () => {
    h.selected = {
      teamId: "team-1",
      selectedTeam: team(["can_read", "can_update_resources", "can_update_agents"]),
      isPersonalTeam: false,
    };
    const html = render();
    expect(html).toContain("rework.teamUsage.team.pageTitle");
    expect(html).not.toContain("rework.teamUsage.title");
    expect(html).toContain("rework.teamUsage.team.sectionTitle");
  });

  it("shows the shared team section and the team title for team_admin (can_update_info)", () => {
    h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_update_info"]), isPersonalTeam: false };
    const html = render();
    expect(html).toContain("rework.teamUsage.team.pageTitle");
    expect(html).not.toContain("rework.teamUsage.title");
    expect(html).toContain("rework.teamUsage.team.sectionTitle");
  });
});

it("hides previous scope/range skill results while the current request is fetching", () => {
  h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_update_resources"]), isPersonalTeam: false };
  const previous = h.skillQuery.getMockImplementation();
  h.skillQuery.mockReturnValue({
    data: {
      rows: [{ skill_name: "stale-skill", user_count: 9, model_count: 1, total: 10 }],
      since: "old",
      until: "old",
    },
    currentData: undefined,
    isLoading: false,
    isFetching: true,
    isError: false,
  });
  try {
    const html = renderToStaticMarkup(<TeamUsagePage />);
    expect(html).not.toContain("stale-skill");
    expect(html).toContain("common.loading");
    expect(html).not.toContain("rework.analytics.skillUsage.empty");
  } finally {
    h.skillQuery.mockImplementation(previous!);
  }
});

it("does not substitute personal skills for unauthorized team counts in team space", () => {
  h.selected = {
    teamId: "team-member",
    selectedTeam: team(["can_read", "can_use_team_agents"]),
    isPersonalTeam: false,
  };
  const html = render();
  expect(html).not.toContain("rework.teamUsage.personalSkillsSectionTitle");
  expect(html).not.toContain("rework.teamUsage.team.skillsSectionTitle");
  expect(h.personalSkillQuery).toHaveBeenLastCalledWith(
    { since: expect.any(String), until: expect.any(String) },
    { skip: true, refetchOnMountOrArgChange: 300 },
  );
  expect(h.skillQuery).toHaveBeenLastCalledWith(expect.anything(), { skip: true, refetchOnMountOrArgChange: 300 });
});

it("shows only team skills for an elevated viewer in team space", () => {
  h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_update_resources"]), isPersonalTeam: false };
  const html = render();
  expect(html).toContain("rework.teamUsage.team.skillsSectionTitle");
  expect(html).not.toContain("rework.teamUsage.personalSkillsSectionTitle");
  expect(html.match(/aria-label="rework.analytics.skillUsage.title"/g)).toHaveLength(1);
  expect(h.skillQuery).toHaveBeenLastCalledWith(expect.objectContaining({ teamId: "team-1" }), {
    skip: false,
    refetchOnMountOrArgChange: 300,
  });
  expect(h.personalSkillQuery).toHaveBeenLastCalledWith(
    { since: expect.any(String), until: expect.any(String) },
    { skip: true, refetchOnMountOrArgChange: 300 },
  );
});

it("does not render cached personal skill counts after selecting team space", () => {
  h.selected = { teamId: "team-1", selectedTeam: team(["can_read", "can_update_resources"]), isPersonalTeam: false };
  const previous = h.personalSkillQuery.getMockImplementation();
  const personalData = {
    rows: [{ skill_name: "personal-only-skill", user_count: 8, model_count: 1, total: 9 }],
    since: "old",
    until: "old",
  };
  h.personalSkillQuery.mockReturnValue({
    data: personalData,
    currentData: personalData,
    isLoading: false,
    isFetching: false,
    isError: false,
  });
  try {
    const html = render();
    expect(html).not.toContain("personal-only-skill");
    expect(html.match(/aria-label="rework.analytics.skillUsage.title"/g)).toHaveLength(1);
  } finally {
    h.personalSkillQuery.mockImplementation(previous!);
  }
});

it("keeps personal skills visible in personal space and suppresses stale personal data", () => {
  h.selected = { teamId: "personal-u1", selectedTeam: undefined, isPersonalTeam: true };
  const previous = h.personalSkillQuery.getMockImplementation();
  h.personalSkillQuery.mockReturnValue({
    data: {
      rows: [{ skill_name: "old-personal-skill", user_count: 10, model_count: 1, total: 11 }],
      since: "old",
      until: "old",
    },
    currentData: undefined,
    isLoading: false,
    isFetching: true,
    isError: false,
  });
  try {
    const html = render();
    expect(html).toContain("rework.teamUsage.personalSkillsSectionTitle");
    expect(html).not.toContain("rework.teamUsage.team.skillsSectionTitle");
    expect(html).not.toContain("old-personal-skill");
    expect(html).toContain("common.loading");
    expect(html.match(/aria-label="rework.analytics.skillUsage.title"/g)).toHaveLength(1);
    expect(h.personalSkillQuery).toHaveBeenLastCalledWith(
      { since: expect.any(String), until: expect.any(String) },
      { skip: false, refetchOnMountOrArgChange: 300 },
    );
  } finally {
    h.personalSkillQuery.mockImplementation(previous!);
  }
});

it.each([
  { space: "personal", personal: true, permissions: [] as TeamPermission[] },
  { space: "team member", personal: false, permissions: ["can_read", "can_use_team_agents"] as TeamPermission[] },
  { space: "team editor", personal: false, permissions: ["can_read", "can_update_resources"] as TeamPermission[] },
])("preserves the full service outage notice in $space space", ({ personal, permissions }) => {
  h.selected = {
    teamId: personal ? "personal-u1" : "team-1",
    selectedTeam: team(permissions),
    isPersonalTeam: personal,
  };
  const previousNeutral = h.neutralQuery.getMockImplementation();
  const previousPersonal = h.personalSkillQuery.getMockImplementation();
  const previousTeam = h.skillQuery.getMockImplementation();
  h.neutralQuery.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, isError: true });
  const failed = { data: undefined, currentData: undefined, isLoading: false, isFetching: false, isError: true };
  h.personalSkillQuery.mockReturnValue(failed);
  h.skillQuery.mockReturnValue(failed);
  try {
    const html = render();
    expect(html).toContain("rework.serviceNotice.controlPlane.title");
    expect(html).not.toContain("rework.analytics.skillUsage.title");
  } finally {
    h.neutralQuery.mockImplementation(previousNeutral!);
    h.personalSkillQuery.mockImplementation(previousPersonal!);
    h.skillQuery.mockImplementation(previousTeam!);
  }
});
