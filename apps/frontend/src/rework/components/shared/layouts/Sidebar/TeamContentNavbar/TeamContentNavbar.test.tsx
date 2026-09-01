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

import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  isPersonalTeam: false,
  applicationsEnabled: false,
  result: { data: undefined, isError: false } as {
    data?: { items: Array<Record<string, unknown>> };
    isError: boolean;
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: "/team/team-1/agents" }),
  useNavigate: () => vi.fn(),
  NavLink: ({ to, children }: { to: string; children: ReactNode | ((args: { isActive: boolean }) => ReactNode) }) => (
    <a href={to}>{typeof children === "function" ? children({ isActive: false }) : children}</a>
  ),
}));
vi.mock("../../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy", agentsNicknamePlural: "agents" }),
}));
vi.mock("../../../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({
    teamId: "team-1",
    isPersonalTeam: h.isPersonalTeam,
    selectedTeam: { id: "team-1", name: "Team One", is_member: true, my_relations: ["team_member"] },
    canOpenTeamSettings: false,
  }),
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canUpdateAgents: false, canUpdateInfo: false }),
}));
vi.mock("@hooks/useFrontendFeatureFlag.ts", () => ({
  useFrontendFeatureFlag: () => ({ enabled: h.applicationsEnabled, isLoading: false }),
}));
vi.mock("@hooks/teamCapabilities.ts", () => ({ hasElevatedTeamRole: () => false }));
vi.mock("@rework/features/applications/useTeamApplications.ts", () => ({
  useTeamApplications: () => h.result,
}));
vi.mock("@shared/organisms/ChatList/ChatList.tsx", () => ({ default: () => <div data-chat-list /> }));

import TeamContentNavbar from "./TeamContentNavbar.tsx";

const application = {
  id: "example",
  version: "1.0.0",
  name: { en: "Example" },
  description: { en: "An example application" },
  icon: "extension",
  ui_prefix: "/apps/example",
};

describe("TeamContentNavbar applications entry", () => {
  beforeEach(() => {
    h.isPersonalTeam = false;
    h.applicationsEnabled = false;
    h.result = { data: undefined, isError: false };
  });

  it("adds exactly one generic Apps entry when an authorized app is available", () => {
    h.applicationsEnabled = true;
    h.result.data = { items: [application] };
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html.match(/href="\/team\/team-1\/apps"/g)).toHaveLength(1);
    expect(html).toContain("rework.sidebar.team.menu.apps");
    expect(html).not.toContain(application.id);
  });

  it("hides Apps when the catalog is unavailable, empty, or failed", () => {
    h.applicationsEnabled = true;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');

    h.result = { data: { items: [] }, isError: false };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');

    h.result = { data: { items: [application] }, isError: true };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');
  });

  // Fred no longer compiles application code, so an app version Fred has never
  // heard of is ordinary — it must not suppress the entry the way a build-time
  // registry miss once did.
  it("shows Apps for an application version this Fred build predates", () => {
    h.applicationsEnabled = true;
    h.result = { data: { items: [{ ...application, version: "2.0.0" }] }, isError: false };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain('href="/team/team-1/apps"');
  });

  it("never shows Apps for a personal space", () => {
    h.applicationsEnabled = true;
    h.isPersonalTeam = true;
    h.result = { data: { items: [application] }, isError: false };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');
  });

  it("hides Apps behind the default-off deployment switch despite a compatible cached catalog", () => {
    h.result.data = { items: [application] };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');
  });
});
