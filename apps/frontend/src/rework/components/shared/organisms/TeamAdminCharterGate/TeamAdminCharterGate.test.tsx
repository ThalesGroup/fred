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

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({ team: undefined as { id: string; my_relations: string[] } | undefined }));

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

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamAdminCharterGate>team-pages</TeamAdminCharterGate>);
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
  it("shows the charter instead of the pages of a team the user is a pending admin of", () => {
    h.team = { id: "team-1", my_relations: ["pending_team_admin", "team_editor"] };
    render();

    expect(container.textContent).toBe("charter-page");
  });

  it("leaves a team's pages to its admins and members", () => {
    h.team = { id: "team-1", my_relations: ["team_admin"] };
    render();

    expect(container.textContent).toBe("team-pages");
  });

  it("never blocks the home page, where no team is selected", () => {
    render();

    expect(container.textContent).toBe("team-pages");
  });
});
