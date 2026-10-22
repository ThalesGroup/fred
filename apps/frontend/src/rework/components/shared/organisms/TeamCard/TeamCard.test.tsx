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

// The marketplace card's join affordance is driven entirely by `joining_mode`
// (+ `is_member`): a direct self-service join button for OPEN, an "invite only"
// label for every INVITE_ONLY case, plus the join mutation firing for OPEN;
// ON_REQUEST cards follow the caller's own request (ask, sent, declined).

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
  askToJoin: vi.fn((_arg: unknown) => ({ unwrap: () => Promise.resolve({}) })),
  showError: vi.fn(),
  cancelRequest: vi.fn((_arg: unknown) => ({ unwrap: () => Promise.resolve({}) })),
  isJoining: false,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useJoinTeamMutation: () => [h.joinTeam, { isLoading: h.isJoining }],
  useAskToJoinTeamMutation: () => [h.askToJoin, { isLoading: false }],
  useCancelTeamJoinRequestMutation: () => [h.cancelRequest, { isLoading: false }],
}));

// The shared Dialog portals out of the card; a stand-in keeps the body inline.
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: h.showError }) }));
vi.mock("@shared/molecules/Dialog/Dialog.tsx", () => ({
  Dialog: ({
    open,
    title,
    children,
    confirmLabel,
    onConfirm,
  }: {
    open: boolean;
    title: string;
    children: React.ReactNode;
    confirmLabel: string;
    onConfirm: () => void;
  }) =>
    open ? (
      <div role="dialog" aria-label={title}>
        {children}
        <button onClick={onConfirm}>{confirmLabel}</button>
      </div>
    ) : null,
}));

vi.mock("src/hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: undefined }),
}));

vi.mock("src/hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({
    defaultTeamAvatarFile: undefined,
    defaultPersonalAvatarFile: undefined,
  }),
}));

vi.mock("../../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: { GetUserFullName: () => "Test User", GetUserName: () => "test.user" },
}));

import TeamCard from "./TeamCard.tsx";

const admin = { id: "u-1", first_name: "Ay", last_name: "One", email: "ay@example.com" };

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
  h.askToJoin.mockClear();
  h.showError.mockClear();
  h.cancelRequest.mockClear();
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
    render(<TeamCard team={baseTeam({ joining_mode: "open" })} onJoined={onJoined} />);

    const button = container.querySelector("button");
    expect(button).not.toBeNull();
    expect(button?.textContent).toContain("rework.teamCard.join");

    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(h.joinTeam).toHaveBeenCalledWith({ teamId: "team-1" });
  });

  it("INVITE_ONLY + public with reachable admins: no button, shows the invite-only label", () => {
    // Formerly a prefilled mailto button; the marketplace no longer offers one.
    render(<TeamCard team={baseTeam({ joining_mode: "invite_only", visibility: "public", admins: [admin] })} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  });

  it("INVITE_ONLY + private: no button, shows the invite-only label", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "invite_only", visibility: "private", admins: [admin] })} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  });

  it("already a member: no join button or label regardless of joining_mode", () => {
    render(<TeamCard team={baseTeam({ joining_mode: "open", is_member: true })} />);

    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).not.toContain("rework.teamCard.join");
  });
});

describe("TeamCard admin avatars", () => {
  it("shows an admin's picture and falls back to initials for an admin without one", () => {
    const withPicture = { ...admin, avatar_image_url: "https://objects.test/ay.webp" };
    const withoutPicture = { id: "u-2", first_name: "Bea", last_name: "Two" };
    render(<TeamCard team={baseTeam({ joining_mode: "invite_only", admins: [withPicture, withoutPicture] })} />);

    const images = Array.from(container.querySelectorAll("img")).map((img) => img.getAttribute("src"));
    expect(images).toContain("https://objects.test/ay.webp");
    expect(container.textContent).toContain("BT");
  });
});

describe("TeamCard description", () => {
  it("shows the description on a member's card as well as a discover card", () => {
    render(<TeamCard team={baseTeam({ is_member: true, description: "Prepare board meeting briefs." })} />);
    expect(container.textContent).toContain("Prepare board meeting briefs.");
    act(() => root.unmount());
    container.remove();

    render(<TeamCard team={baseTeam({ is_member: false, description: "Answer internal IT questions." })} />);
    expect(container.textContent).toContain("Answer internal IT questions.");
  });

  it("shows the translated text instead of the stored placeholder", () => {
    render(
      <TeamCard
        team={baseTeam({
          description: "Description à compléter par l'administrateur de l'équipe.",
          description_is_placeholder: true,
        })}
      />,
    );
    expect(container.textContent).toContain("rework.teamDescription.placeholderDisplay");
    expect(container.textContent).not.toContain("Description à compléter");
  });
});

const HOUR = 3_600_000;
const buttonByLabel = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes(label));
const click = (element: Element | undefined) =>
  act(() => {
    element?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });

describe("TeamCard on_request", () => {
  const onRequestTeam = baseTeam({ joining_mode: "on_request", visibility: "public" });

  it("without a request: Ask to join opens the dialog and sends the trimmed message", async () => {
    render(<TeamCard team={onRequestTeam} />);
    expect(container.querySelector('[role="dialog"]')).toBeNull();

    click(buttonByLabel("rework.teamCard.askToJoin"));
    const textarea = container.querySelector("textarea")!;
    expect(textarea.maxLength).toBe(280);
    expect(container.textContent).toContain("rework.teamCard.askDialog.messageDescription");
    expect(container.textContent).toContain("0 / 280");

    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      setter.call(textarea, "  I run the RFP pipeline.  ");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      buttonByLabel("rework.teamCard.askDialog.confirm")?.click();
    });

    expect(h.askToJoin).toHaveBeenCalledWith({
      teamId: "team-1",
      createTeamJoinRequest: { message: "I run the RFP pipeline." },
    });
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("a failed request keeps the dialog open and says why", async () => {
    h.askToJoin.mockReturnValueOnce({ unwrap: () => Promise.reject({ status: 409, data: { detail: "Refused" } }) });
    render(<TeamCard team={onRequestTeam} />);
    click(buttonByLabel("rework.teamCard.askToJoin"));

    await act(async () => {
      buttonByLabel("rework.teamCard.askDialog.confirm")?.click();
    });

    expect(h.showError).toHaveBeenCalledWith(
      expect.objectContaining({ summary: "rework.teamCard.askDialog.failed", detail: "Refused" }),
    );
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
  });

  it("an empty message is sent as none", async () => {
    render(<TeamCard team={onRequestTeam} />);
    click(buttonByLabel("rework.teamCard.askToJoin"));
    await act(async () => {
      buttonByLabel("rework.teamCard.askDialog.confirm")?.click();
    });
    expect(h.askToJoin).toHaveBeenCalledWith({ teamId: "team-1", createTeamJoinRequest: { message: null } });
  });

  it("pending: shows Request sent and cancels it", () => {
    render(
      <TeamCard
        team={onRequestTeam}
        joinRequest={{ id: "r1", team_id: "team-1", status: "pending", created_at: new Date().toISOString() }}
      />,
    );
    expect(container.textContent).toContain("rework.teamCard.requestSent");
    expect(buttonByLabel("rework.teamCard.askToJoin")).toBeUndefined();

    click(buttonByLabel("rework.teamCard.cancelRequest"));
    expect(h.cancelRequest).toHaveBeenCalledWith({ teamId: "team-1" });
  });

  it("refused less than 24 hours ago: Request declined with when to ask again, no button", () => {
    render(
      <TeamCard
        team={onRequestTeam}
        joinRequest={{
          id: "r1",
          team_id: "team-1",
          status: "refused",
          created_at: new Date(Date.now() - 2 * HOUR).toISOString(),
          decided_at: new Date(Date.now() - HOUR).toISOString(),
          can_ask_again_at: new Date(Date.now() + 23 * HOUR).toISOString(),
        }}
      />,
    );
    expect(container.textContent).toContain("rework.teamCard.requestDeclined");
    expect(container.textContent).toContain("rework.teamCard.askAgainAt");
    expect(container.querySelector("button")).toBeNull();
  });

  it("refused more than 24 hours ago: Ask to join again", () => {
    render(
      <TeamCard
        team={onRequestTeam}
        joinRequest={{
          id: "r1",
          team_id: "team-1",
          status: "refused",
          created_at: new Date(Date.now() - 30 * HOUR).toISOString(),
          can_ask_again_at: new Date(Date.now() - HOUR).toISOString(),
        }}
      />,
    );
    expect(buttonByLabel("rework.teamCard.askToJoin")).toBeDefined();
    expect(container.textContent).not.toContain("rework.teamCard.requestDeclined");
  });

  it("a member of an on_request team sees no request affordance", () => {
    render(<TeamCard team={{ ...onRequestTeam, is_member: true }} />);
    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).not.toContain("rework.teamCard.requestSent");
  });
});
