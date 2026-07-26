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
import type { TeamMember, TeamWithPermissions } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  teamMembers: [] as TeamMember[],
  grantTeamMemberRole: vi.fn(),
  revokeTeamMemberRole: vi.fn(),
  removeTeamMember: vi.fn(),
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
  useListTeamMembersQuery: () => ({ data: h.teamMembers }),
  useGrantTeamMemberRoleMutation: () => [h.grantTeamMemberRole],
  useRevokeTeamMemberRoleMutation: () => [h.revokeTeamMemberRole],
  useRemoveTeamMemberMutation: () => [h.removeTeamMember],
}));

import TeamSettingsMembersTable from "./TeamSettingsMembersTable.tsx";
import { ConfirmationDialogProvider } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider.tsx";

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
  h.grantTeamMemberRole.mockReset();
  h.revokeTeamMemberRole.mockReset();
  h.removeTeamMember.mockReset();
  h.teamMembers = [];
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

function roleChip(role: string): HTMLButtonElement {
  const label = `rework.teamRoles.${role}`;
  return Array.from(container.querySelectorAll("button")).find((b) => b.textContent === label) as HTMLButtonElement;
}

describe("TeamSettingsMembersTable — revoke confirmation", () => {
  it("clicking an already-active role chip does not revoke immediately — it opens a confirmation first", () => {
    h.teamMembers = [
      {
        user: { id: "u1", first_name: "Alice", last_name: "Doe", username: "alice" },
        relations: ["team_editor"],
      } as TeamMember,
    ];
    render(
      <ConfirmationDialogProvider>
        <TeamSettingsMembersTable team={team} />
      </ConfirmationDialogProvider>,
    );

    click(roleChip("team_editor"));

    expect(h.revokeTeamMemberRole).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
  });

  it("confirming the dialog then calls revokeTeamMemberRole for that user and role", () => {
    h.revokeTeamMemberRole.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    h.teamMembers = [
      {
        user: { id: "u1", first_name: "Alice", last_name: "Doe", username: "alice" },
        relations: ["team_editor"],
      } as TeamMember,
    ];
    render(
      <ConfirmationDialogProvider>
        <TeamSettingsMembersTable team={team} />
      </ConfirmationDialogProvider>,
    );

    click(roleChip("team_editor"));
    const confirmButton = Array.from(document.querySelectorAll('[role="alertdialog"] button')).find(
      (b) => b.textContent === "rework.teamSettings.members.revokeRoleDialog.confirmLabel",
    );
    click(confirmButton ?? null);

    expect(h.revokeTeamMemberRole).toHaveBeenCalledWith({
      teamId: "team-1",
      userId: "u1",
      relation: "team_editor",
    });
  });

  it("clicking cancel leaves the role untouched", () => {
    h.teamMembers = [
      {
        user: { id: "u1", first_name: "Alice", last_name: "Doe", username: "alice" },
        relations: ["team_admin"],
      } as TeamMember,
    ];
    render(
      <ConfirmationDialogProvider>
        <TeamSettingsMembersTable team={team} />
      </ConfirmationDialogProvider>,
    );

    click(roleChip("team_admin"));
    const cancelButton = Array.from(document.querySelectorAll('[role="alertdialog"] button')).find(
      (b) => b.textContent === "confirmationDialog.defaultCancelButtonLabel",
    );
    click(cancelButton ?? null);

    expect(h.revokeTeamMemberRole).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it("clicking an inactive role chip still grants immediately with no confirmation", () => {
    h.grantTeamMemberRole.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    h.teamMembers = [
      {
        user: { id: "u1", first_name: "Alice", last_name: "Doe", username: "alice" },
        relations: ["team_member"],
      } as TeamMember,
    ];
    render(
      <ConfirmationDialogProvider>
        <TeamSettingsMembersTable team={team} />
      </ConfirmationDialogProvider>,
    );

    click(roleChip("team_editor"));

    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    expect(h.grantTeamMemberRole).toHaveBeenCalledWith({
      teamId: "team-1",
      userId: "u1",
      grantTeamMemberRoleRequest: { relation: "team_editor" },
    });
  });
});
