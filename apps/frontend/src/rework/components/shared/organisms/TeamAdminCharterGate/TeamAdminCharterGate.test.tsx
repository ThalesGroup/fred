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
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

type SelectedTeam = { id: string; my_relations: string[]; admins: Array<{ id: string }> };

const h = vi.hoisted(() => ({ team: undefined as SelectedTeam | undefined }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({
    teamId: h.team?.id,
    isPersonalTeam: false,
    selectedTeam: h.team,
    canOpenTeamSettings: true,
  }),
}));

vi.mock("@components/pages/TeamAdminCharterPage/TeamAdminCharterPage.tsx", () => ({
  default: () => "charter-page",
}));

import TeamAdminCharterGate from "./TeamAdminCharterGate.tsx";

let container: HTMLDivElement;
let root: Root;

function render(path = "/team/team-1/agents") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <TeamAdminCharterGate>team-pages</TeamAdminCharterGate>
      </MemoryRouter>,
    );
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.team = undefined;
});

describe("TeamAdminCharterGate", () => {
  it("shows the charter instead of the pages of a team with no accepted admin", () => {
    h.team = { id: "team-1", my_relations: ["pending_team_admin", "team_editor"], admins: [] };
    render();

    expect(container.textContent).toBe("charter-page");
  });

  it("leaves the pages to a pending admin's other roles once the team has an accepted admin", () => {
    h.team = { id: "team-1", my_relations: ["pending_team_admin", "team_editor"], admins: [{ id: "alice" }] };
    render();

    expect(container.querySelector('[role="status"]')?.textContent).toContain("rework.teamAdminCharter.pendingNotice");
    expect(container.textContent).toContain("team-pages");
    expect(container.querySelector("a")?.getAttribute("href")).toBe("/team/team-1/settings/responsibilities");
  });

  it("drops the notice on the Responsibilities section, which holds the Accept action", () => {
    h.team = { id: "team-1", my_relations: ["pending_team_admin"], admins: [{ id: "alice" }] };
    render("/team/team-1/settings/responsibilities");

    expect(container.textContent).toBe("team-pages");
  });

  it("leaves a team's pages to its admins and members", () => {
    h.team = { id: "team-1", my_relations: ["team_admin"], admins: [{ id: "alice" }] };
    render();

    expect(container.textContent).toBe("team-pages");
  });

  it("never blocks the home page, where no team is selected", () => {
    render("/");

    expect(container.textContent).toBe("team-pages");
  });
});
