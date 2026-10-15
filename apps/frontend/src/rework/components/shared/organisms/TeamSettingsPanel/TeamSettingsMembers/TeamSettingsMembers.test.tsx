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

const h = vi.hoisted(() => ({ canAdministerMembers: true, manager: vi.fn() }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canAdministerMembers: h.canAdministerMembers }),
}));
vi.mock("./TeamSettingsMembersTable/TeamSettingsMembersTable.tsx", () => ({ default: () => null }));
vi.mock("./TeamSettingsMembersMenu/TeamSettingsMembersMenu.tsx", () => ({ default: () => null }));
vi.mock("./AddTeamMembersDialog/AddTeamMembersDialog.tsx", () => ({ default: () => null }));
vi.mock("../../../../pages/admin/PlatformAccessPage/PlatformAccessLinkManager", () => ({
  default: (props: { scope: string; team: { team_id: string; name: string } }) => {
    h.manager(props);
    return <div data-testid="link-manager" />;
  },
}));

import TeamSettingsMembers from "./TeamSettingsMembers";

const team = { id: "demo", name: "Demonstration" } as TeamWithPermissions;
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
  h.manager.mockClear();
});

it("opens the team's join-link manager next to Add members", () => {
  render();
  const labels = [...container.querySelectorAll("button")].map((node) => node.textContent);
  expect(labels.indexOf("rework.teamSettings.members.inviteLink.buttonLabel")).toBe(
    labels.indexOf("rework.teamSettings.members.addMembersDialog.buttonLabel") - 1,
  );
  expect(container.querySelector('[data-testid="link-manager"]')).toBeNull();
  act(() => inviteButton()!.click());
  expect(container.querySelector('[data-testid="link-manager"]')).not.toBeNull();
  expect(h.manager).toHaveBeenCalledWith(
    expect.objectContaining({ scope: "team", team: { team_id: "demo", name: "Demonstration" } }),
  );
});

it("hides the invite link from people who cannot administer members", () => {
  h.canAdministerMembers = false;
  render();
  expect(inviteButton()).toBeUndefined();
});
