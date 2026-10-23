// @vitest-environment happy-dom
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import type { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({ canAdministerMembers: true, platformAccess: true, dialog: vi.fn(), section: vi.fn() }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canAdministerMembers: h.canAdministerMembers }),
}));
vi.mock("./TeamSettingsMembersTable/TeamSettingsMembersTable.tsx", () => ({ default: () => null }));
vi.mock("./TeamSettingsMembersMenu/TeamSettingsMembersMenu.tsx", () => ({ default: () => null }));
vi.mock("./AddTeamMembersDialog/AddTeamMembersDialog.tsx", () => ({ default: () => null }));
vi.mock("./TeamJoinRequestsSection/TeamJoinRequestsSection.tsx", () => ({
  default: (props: { teamId: string; canAdministerMembers: boolean }) => {
    h.section(props);
    return null;
  },
}));
vi.mock("../../../../../../common/config", () => ({
  getConfig: () => ({ platform_access_enabled: h.platformAccess }),
}));
vi.mock("./TeamInviteLinkDialog/TeamInviteLinkDialog.tsx", () => ({
  default: (props: { teamId: string }) => {
    h.dialog(props);
    return <div data-testid="invite-link-dialog" />;
  },
}));

import TeamSettingsMembers from "./TeamSettingsMembers";

const team = {
  id: "demo",
  name: "Demonstration",
  visibility: "public",
  joining_mode: "on_request",
} as TeamWithPermissions;
let container: HTMLDivElement;
let root: Root;

const render = () => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<TeamSettingsMembers team={team} />));
};
const inviteButton = () =>
  [...container.querySelectorAll("button")].find((node) =>
    node.textContent?.includes("rework.teamSettings.members.inviteLink.buttonLabel"),
  );

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  h.canAdministerMembers = true;
  h.platformAccess = true;
  h.dialog.mockClear();
  h.section.mockClear();
});

it("hands the pending requests section the team, the caller's right to decide and the team's mode", () => {
  h.canAdministerMembers = false;
  render();
  expect(h.section).toHaveBeenCalledWith({ teamId: "demo", canAdministerMembers: false, takesRequests: true });
});

it("opens the team's invite link dialog next to Add members", () => {
  render();
  const labels = [...container.querySelectorAll("button")].map((node) => node.textContent);
  expect(labels.indexOf("rework.teamSettings.members.inviteLink.buttonLabel")).toBe(
    labels.indexOf("rework.teamSettings.members.addMembersDialog.buttonLabel") - 1,
  );
  expect(container.querySelector('[data-testid="invite-link-dialog"]')).toBeNull();
  act(() => inviteButton()!.click());
  expect(container.querySelector('[data-testid="invite-link-dialog"]')).not.toBeNull();
  expect(h.dialog).toHaveBeenCalledWith(expect.objectContaining({ teamId: "demo" }));
});

it("hides the invite link from people who cannot administer members", () => {
  h.canAdministerMembers = false;
  render();
  expect(inviteButton()).toBeUndefined();
});

it("hides the invite link when the deployment has no platform access", () => {
  h.platformAccess = false;
  render();
  expect(inviteButton()).toBeUndefined();
  expect(container.textContent).toContain("rework.teamSettings.members.addMembersDialog.buttonLabel");
});
