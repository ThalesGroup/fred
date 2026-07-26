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
import type { TeamWithPermissions, UserSummary } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  addTeamMember: vi.fn(),
  grantTeamMemberRole: vi.fn(),
  candidates: [] as UserSummary[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

vi.mock("../../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAddTeamMemberMutation: () => [h.addTeamMember],
  useGrantTeamMemberRoleMutation: () => [h.grantTeamMemberRole],
  useSearchCandidateTeamMembersQuery: () => ({ data: h.candidates }),
}));

import AddTeamMembersDialog from "./AddTeamMembersDialog.tsx";

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
  document.getElementById("modal-portal")?.remove();
  h.addTeamMember.mockReset();
  h.grantTeamMemberRole.mockReset();
  h.candidates = [];
});

function click(el: Element | null) {
  if (!el) throw new Error("element not found");
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

const team: TeamWithPermissions = {
  id: "team-1",
  name: "Team One",
  is_member: true,
  admins: [],
  permissions: ["can_administer_members", "can_administer_editors", "can_administer_analysts", "can_administer_admins"],
} as TeamWithPermissions;

const alice: UserSummary = { id: "u1", first_name: "Alice", last_name: "Doe", username: "alice" };

function portal(): HTMLElement {
  const el = document.getElementById("modal-portal");
  if (!el) throw new Error("dialog portal not rendered");
  return el;
}

function confirmButton(): HTMLButtonElement {
  return Array.from(portal().querySelectorAll("button")).find(
    (b) => b.textContent === "rework.teamSettings.members.addMembersDialog.confirm",
  ) as HTMLButtonElement;
}

const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;

/** Types into the search field so the component re-renders and picks up the
 *  (mutated) mocked candidate list, then clicks the matching menu option. */
function selectCandidate(user: UserSummary) {
  h.candidates = [user];
  const input = portal().querySelector("input") as HTMLInputElement;
  act(() => {
    nativeInputValueSetter.call(input, user.username);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const option = Array.from(portal().querySelectorAll('[role="option"]')).find((o) =>
    o.textContent?.includes(user.username!),
  );
  click(option ?? null);
}

function roleChip(role: string): HTMLButtonElement {
  const label = `rework.teamRoles.${role}`;
  return Array.from(portal().querySelectorAll("button")).find((b) => b.textContent === label) as HTMLButtonElement;
}

describe("AddTeamMembersDialog", () => {
  it("renders nothing when closed", () => {
    render(<AddTeamMembersDialog open={false} team={team} onClose={vi.fn()} />);
    expect(document.getElementById("modal-portal")).toBeNull();
  });

  it("shows the header and a disabled confirm button with an empty pending list", () => {
    render(<AddTeamMembersDialog open={true} team={team} onClose={vi.fn()} />);
    expect(portal().textContent).toContain("rework.teamSettings.members.addMembersDialog.title");
    expect(portal().textContent).toContain("rework.teamSettings.members.addMembersDialog.subtitle");
    expect(confirmButton().disabled).toBe(true);
  });

  it("selecting a candidate adds a pending row and enables confirm", () => {
    render(<AddTeamMembersDialog open={true} team={team} onClose={vi.fn()} />);
    selectCandidate(alice);

    expect(portal().textContent).toContain("Alice Doe (alice)");
    expect(confirmButton().disabled).toBe(false);
  });

  it("removing a pending row via its delete button clears it and disables confirm again", () => {
    render(<AddTeamMembersDialog open={true} team={team} onClose={vi.fn()} />);
    selectCandidate(alice);

    const removeButton = Array.from(portal().querySelectorAll("button")).find((b) =>
      b.getAttribute("aria-label")?.startsWith("rework.teamSettings.members.addMembersDialog.removeAria"),
    );
    click(removeButton ?? null);

    // The removed candidate becomes searchable again, so it can still appear
    // in the (closed) suggestions dropdown — assert on the pending list
    // specifically, not the whole dialog's text.
    expect(portal().querySelector('[class*="pendingList"]')).toBeNull();
    expect(confirmButton().disabled).toBe(true);
  });

  it("confirming with no role selected adds the user with the team_member baseline", async () => {
    h.addTeamMember.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    const onClose = vi.fn();
    render(<AddTeamMembersDialog open={true} team={team} onClose={onClose} />);
    selectCandidate(alice);

    await act(async () => {
      click(confirmButton());
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(h.addTeamMember).toHaveBeenCalledWith({
      teamId: "team-1",
      addTeamMemberRequest: { user_id: "u1", relation: "team_member" },
    });
    expect(h.grantTeamMemberRole).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("confirming with two selected roles adds with the highest-priority role and grants the other", async () => {
    h.addTeamMember.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    h.grantTeamMemberRole.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    render(<AddTeamMembersDialog open={true} team={team} onClose={vi.fn()} />);
    selectCandidate(alice);

    click(roleChip("team_editor"));
    click(roleChip("team_analyst"));

    await act(async () => {
      click(confirmButton());
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(h.addTeamMember).toHaveBeenCalledWith({
      teamId: "team-1",
      addTeamMemberRequest: { user_id: "u1", relation: "team_editor" },
    });
    expect(h.grantTeamMemberRole).toHaveBeenCalledWith({
      teamId: "team-1",
      userId: "u1",
      grantTeamMemberRoleRequest: { relation: "team_analyst" },
    });
  });

  it("keeps a failed user in the pending list and does not close the dialog", async () => {
    h.addTeamMember.mockReturnValue({ unwrap: () => Promise.reject(new Error("boom")) });
    const onClose = vi.fn();
    render(<AddTeamMembersDialog open={true} team={team} onClose={onClose} />);
    selectCandidate(alice);

    await act(async () => {
      click(confirmButton());
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(portal().textContent).toContain("Alice Doe (alice)");
    expect(onClose).not.toHaveBeenCalled();
  });
});
