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

import type { ReactNode } from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  section: "members" as string,
  relations: [] as string[],
  charterRequired: false,
  charterQueryOptions: undefined as { skip: boolean; refetchOnMountOrArgChange?: boolean } | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("react-router-dom", () => ({
  useParams: () => ({ section: h.section }),
  Navigate: ({ to }: { to: string }) => `navigate:${to}`,
  Link: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({
    teamId: "team-1",
    selectedTeam: { id: "team-1", permissions: [], my_relations: h.relations },
    canOpenTeamSettings: true,
  }),
}));

vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canUpdateInfo: false, canUpdateAgents: false, canUpdateResources: false }),
}));

vi.mock("@hooks/teamCapabilities.ts", () => ({ hasElevatedTeamRole: () => false }));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useTeamAdminCharterStatusQuery: (_arg: unknown, options: { skip: boolean; refetchOnMountOrArgChange?: boolean }) => {
    h.charterQueryOptions = options;
    return { data: options.skip ? undefined : { required: h.charterRequired, accepted_at: null } };
  },
}));

vi.mock("@shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamSettingsMembers.tsx", () => ({
  default: () => "members-section",
}));
vi.mock("@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters.tsx", () => ({
  default: () => "parameters-section",
}));
vi.mock("@shared/organisms/TeamSettingsPanel/TeamSettingsEvaluations/TeamSettingsEvaluations.tsx", () => ({
  default: () => "evaluations-section",
}));
vi.mock("@shared/organisms/TeamSettingsPanel/TeamSettingsRouting/TeamSettingsRouting.tsx", () => ({
  default: () => "routing-section",
}));
vi.mock("@shared/organisms/TaskActivity/TaskActivity.tsx", () => ({ default: () => "activity-section" }));
vi.mock("@shared/organisms/TeamSettingsPanel/TeamSettingsResponsibilities/TeamSettingsResponsibilities.tsx", () => ({
  default: () => "responsibilities-section",
}));
vi.mock("@shared/molecules/ServiceNotice/ServiceNotice.tsx", () => ({
  default: ({ title }: { title: string }) => title,
}));
vi.mock("@shared/atoms/Button/Button.tsx", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));

import TeamSettingsPage from "./TeamSettingsPage.tsx";

let container: HTMLDivElement;
let root: Root;

function render(section: string, relations: string[], charterRequired = false) {
  h.section = section;
  h.relations = relations;
  h.charterRequired = charterRequired;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamSettingsPage />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("TeamSettingsPage responsibilities", () => {
  it("shows the Responsibilities section to a team admin", () => {
    render("responsibilities", ["team_admin"]);

    expect(container.textContent).toBe("responsibilities-section");
  });

  it("redirects a plain member away from the Responsibilities section", () => {
    render("responsibilities", ["team_member"]);

    expect(container.textContent).toBe("navigate:/team/team-1/settings/members");
  });

  it("tells a pending admin their rights are inactive and leads to the charter", () => {
    render("members", ["team_admin"], true);

    expect(container.textContent).toContain("rework.teamAdminCharter.pendingNotice");
    expect(container.textContent).toContain("rework.teamAdminCharter.reviewCharter");
    expect(container.textContent).toContain("members-section");
  });

  it("reads the charter status again on every visit", () => {
    render("members", ["team_admin"]);

    expect(h.charterQueryOptions).toEqual({ skip: false, refetchOnMountOrArgChange: true });
  });

  it("shows no notice once nothing is pending", () => {
    render("members", ["team_admin"], false);

    expect(container.textContent).toBe("members-section");
  });
});
