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
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  team: undefined as Record<string, unknown> | undefined,
  error: undefined as unknown,
  requests: [] as Array<{ team_id: string; status: string }>,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({ activeTeam: { id: "personal-me" } }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: (_args: unknown, { skip }: { skip: boolean }) =>
    skip ? { isFetching: false } : { data: h.team, error: h.error, isFetching: false },
  useMyTeamJoinRequestsQuery: () => ({ data: h.requests }),
  useAskToJoinTeamMutation: () => [vi.fn(), { isLoading: false }],
}));

vi.mock("@shared/molecules/Dialog/Dialog.tsx", () => ({
  Dialog: () => null,
}));

import TeamMemberGate from "./TeamMemberGate.tsx";

let container: HTMLDivElement;
let root: Root;

function render(path = "/team/team-1/agents") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/team/:teamId/*" element={<TeamMemberGate>team-pages</TeamMemberGate>} />
          <Route path="/home" element={<TeamMemberGate>home-page</TeamMemberGate>} />
        </Routes>
      </MemoryRouter>,
    );
  });
}

const team = (overrides: Record<string, unknown> = {}) => ({
  id: "team-1",
  name: "Atlas",
  is_member: false,
  visibility: "public",
  joining_mode: "on_request",
  ...overrides,
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  h.team = undefined;
  h.error = undefined;
  h.requests = [];
});

describe("TeamMemberGate", () => {
  it("lets a member through", () => {
    h.team = team({ is_member: true });
    render();
    expect(container.textContent).toBe("team-pages");
  });

  it("does not gate pages outside a team, nor the personal space", () => {
    render("/home");
    expect(container.textContent).toBe("home-page");
    act(() => root.unmount());
    container.remove();
    render("/team/personal-me/agents");
    expect(container.textContent).toBe("team-pages");
  });

  it("offers to ask to join a public on_request team", () => {
    h.team = team();
    render();
    expect(container.textContent).toContain("rework.teamMemberGate.title");
    expect(container.textContent).toContain("rework.teamCard.askToJoin");
    expect(container.textContent).not.toContain("team-pages");
  });

  it("says a pending request is waiting and points to the teams instead", () => {
    h.team = team();
    h.requests = [{ team_id: "team-1", status: "pending" }];
    render();
    expect(container.textContent).toContain("rework.teamMemberGate.pending");
    expect(container.textContent).toContain("rework.teamMemberGate.browseTeams");
    expect(container.textContent).not.toContain("rework.teamCard.askToJoin");
  });

  it("points an outsider of an open or invite-only team to the teams", () => {
    h.team = team({ joining_mode: "invite_only" });
    render();
    expect(container.textContent).toContain("rework.teamMemberGate.browseTeams");
    expect(container.textContent).not.toContain("rework.teamCard.askToJoin");
  });

  it.each([403, 404])("shows the screen when the team answers %i", (status) => {
    h.error = { status, data: { detail: "nope" } };
    render();
    expect(container.textContent).toContain("rework.teamMemberGate.title");
    expect(container.textContent).toContain("rework.teamMemberGate.browseTeams");
  });
});
