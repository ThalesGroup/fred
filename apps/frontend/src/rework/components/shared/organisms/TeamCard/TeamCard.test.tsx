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

// TEAM-09: the marketplace card's join affordance is driven entirely by
// `joining_mode` (+ `is_member`) now that the mailto flow is gone — one
// state per mode, plus the self-service join mutation actually firing for
// OPEN.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  joinTeam: vi.fn(() => ({ unwrap: () => Promise.resolve({}) })),
  isJoining: false,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, opts?: { count?: number }) => (opts ? `${key}:${opts.count}` : key) }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useJoinTeamMutation: () => [h.joinTeam, { isLoading: h.isJoining }],
}));

vi.mock("src/hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: undefined }),
}));

vi.mock("src/hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({
    defaultTeamBannerFile: undefined,
    defaultTeamAvatarFile: undefined,
    defaultPersonalBannerFile: undefined,
    defaultPersonalAvatarFile: undefined,
  }),
}));

vi.mock("../../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: { GetUserFullName: () => "Test User", GetUserName: () => "test.user" },
}));

import TeamCard from "./TeamCard.tsx";

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.joinTeam.mockClear();
  h.isJoining = false;
});

function baseTeam(overrides: Partial<Team>): Team {
  return {
    id: "team-1",
    name: "Team One",
    is_member: false,
    admins: [],
    member_count: 3,
    ...overrides,
  } as Team;
}

describe("TeamCard joining_mode rendering", () => {
  it("OPEN + not a member: shows the join button and calls joinTeam on click", () => {
    const onJoined = vi.fn();
    render(<TeamCard team={baseTeam({ joining_mode: "open" })} withDescription={false} onJoined={onJoined} />);

    const button = container.querySelector("button");
    expect(button).not.toBeNull();
    expect(button?.textContent).toContain("rework.teamCard.join");

    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.joinTeam).toHaveBeenCalledWith({ teamId: "team-1" });
  });

  it("REQUEST_ONLY + not a member: shows a disabled request button", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "request_only" })} withDescription={false} />);

    const button = container.querySelector("button");
    expect(button).not.toBeNull();
    expect(button?.textContent).toContain("rework.teamCard.requestToJoin");
    expect(button?.disabled).toBe(true);
  });

  it("CLOSED + not a member: no button, shows the closed-team label", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "closed" })} withDescription={false} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.closedTeam");
  });

  it("INVITE_ONLY + not a member: no button, shows the invite-only label", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "invite_only" })} withDescription={false} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  });

  it("already a member: no join button or label regardless of joining_mode", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "open", is_member: true })} withDescription={false} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).not.toContain("rework.teamCard.join");
  });
});
