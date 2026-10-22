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
  fetchedAt: Number.MAX_SAFE_INTEGER as number | undefined,
  requests: [] as Array<{ team_id: string; status: string; can_ask_again_at?: string }>,
  listed: [] as Array<{ id: string }>,
  refetchBootstrap: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("../../../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({
    activeTeam: { id: "personal-me" },
    availableTeams: h.listed,
    refetch: h.refetchBootstrap,
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: (_args: unknown, { skip }: { skip: boolean }) =>
    skip ? {} : { data: h.team, error: h.error, fulfilledTimeStamp: h.fetchedAt },
  useMyTeamJoinRequestsQuery: () => ({ data: h.requests }),
  useAskToJoinTeamMutation: () => [vi.fn(), { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));

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
  h.listed = [];
  h.refetchBootstrap.mockClear();
  h.fetchedAt = Number.MAX_SAFE_INTEGER;
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

  it("waits for a fresh answer before showing a team's pages", () => {
    h.team = team({ is_member: true });
    h.fetchedAt = 0; // only a cached answer from before this opening
    render();
    expect(container.textContent).not.toContain("team-pages");
    expect(container.querySelector('[role="status"]')).not.toBeNull();
  });

  it("hides Ask to join while a refusal still makes the person wait", () => {
    h.team = team();
    h.requests = [{ team_id: "team-1", status: "refused", can_ask_again_at: "2999-01-01T00:00:00Z" }];
    render();
    expect(container.textContent).toContain("rework.teamMemberGate.declined");
    expect(container.textContent).toContain("rework.teamMemberGate.browseTeams");
    expect(container.textContent).not.toContain("rework.teamCard.askToJoin");
  });

  it("offers Ask to join again once the wait is over", () => {
    h.team = team();
    h.requests = [{ team_id: "team-1", status: "refused", can_ask_again_at: "2000-01-01T00:00:00Z" }];
    render();
    expect(container.textContent).toContain("rework.teamCard.askToJoin");
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

  it("refreshes the team list when a team it still shows turns the caller away", () => {
    h.listed = [{ id: "team-1" }];
    h.error = { status: 403, data: { detail: "nope" } };
    render();
    expect(h.refetchBootstrap).toHaveBeenCalledTimes(1);
  });

  it("leaves the team list alone for a member", () => {
    h.team = team({ is_member: true });
    h.listed = [{ id: "team-1" }];
    render();
    expect(h.refetchBootstrap).not.toHaveBeenCalled();
  });

  it("leaves the team list alone when it no longer shows the team", () => {
    h.error = { status: 403, data: { detail: "nope" } };
    render();
    expect(h.refetchBootstrap).not.toHaveBeenCalled();
  });
});
