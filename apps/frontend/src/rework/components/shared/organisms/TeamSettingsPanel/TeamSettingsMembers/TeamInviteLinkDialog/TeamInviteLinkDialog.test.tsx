// @vitest-environment happy-dom
// @vitest-environment-options {"url":"http://localhost:5173"}
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  state: { enabled: false, token: null as string | null },
  setEnabled: vi.fn(),
  regenerate: vi.fn(),
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../../../common/platformAccess", () => ({
  platformPath: (path: string) => `/${path.replace(/^\//, "")}`,
}));
vi.mock("../../../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useTeamJoinLinkQuery: () => ({ data: h.state, isFetching: false, isError: false }),
  useSetTeamJoinLinkMutation: () => [h.setEnabled, { isLoading: false }],
  useRegenerateTeamJoinLinkMutation: () => [h.regenerate, { isLoading: false }],
}));

import TeamInviteLinkDialog from "./TeamInviteLinkDialog";

let host: HTMLDivElement;
let root: Root;
const render = () => act(() => root.render(<TeamInviteLinkDialog teamId="demo" onClose={vi.fn()} />));
const button = (key: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) =>
    node.textContent?.includes(`rework.teamSettings.members.inviteLink.${key}`),
  );
const toggle = () => document.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
const urlInput = () => document.querySelector<HTMLInputElement>("input[readonly]");

beforeEach(() => {
  h.state = { enabled: false, token: null };
  h.setEnabled.mockReset().mockReturnValue({ unwrap: async () => undefined });
  h.regenerate.mockReset().mockReturnValue({ unwrap: async () => undefined });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

it("turns the invitation on through the switch, with nothing to copy before", async () => {
  render();
  expect(toggle().checked).toBe(false);
  expect(urlInput()).toBeNull();
  expect(button("regenerate")).toBeUndefined();
  await act(async () => toggle().click());
  expect(h.setEnabled).toHaveBeenCalledWith({ teamId: "demo", setTeamJoinLink: { enabled: true } });
});

it("shows the full link greyed out while the invitation is paused", async () => {
  h.state = { enabled: false, token: "opaque" };
  render();
  expect(urlInput()!.value).toBe("http://localhost:5173/join/opaque");
  expect(urlInput()!.disabled).toBe(true);
  expect(button("copy")!.disabled).toBe(true);
  expect(button("regenerate")!.disabled).toBe(true);
});

it("copies the link and replaces it on request", async () => {
  h.state = { enabled: true, token: "opaque" };
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  render();
  await act(async () => button("copy")!.click());
  expect(writeText).toHaveBeenCalledWith("http://localhost:5173/join/opaque");
  expect(button("copied")).toBeDefined();
  await act(async () => button("regenerate")!.click());
  expect(h.regenerate).toHaveBeenCalledWith({ teamId: "demo" });
  await act(async () => toggle().click());
  expect(h.setEnabled).toHaveBeenCalledWith({ teamId: "demo", setTeamJoinLink: { enabled: false } });
});

it("selects the link when the clipboard refuses", async () => {
  h.state = { enabled: true, token: "opaque" };
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: vi.fn().mockRejectedValue(new Error("no")) } });
  render();
  await act(async () => button("copy")!.click());
  expect(document.querySelector('[role="alert"]')?.textContent).toBe(
    "rework.teamSettings.members.inviteLink.copyFailed",
  );
  const input = urlInput()!;
  expect(document.activeElement).toBe(input);
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, input.value.length]);
});

it("reports a failed update", async () => {
  h.setEnabled.mockReturnValue({
    unwrap: async () => {
      throw new Error("boom");
    },
  });
  render();
  await act(async () => toggle().click());
  expect(document.querySelector('[role="alert"]')?.textContent).toBe("rework.teamSettings.members.inviteLink.failed");
});

it("toggles once from anywhere on the card, and once from the switch itself", async () => {
  render();
  const label = [...document.querySelectorAll("span")].find(
    (node) => node.textContent === "rework.teamSettings.members.inviteLink.enable",
  )!;
  await act(async () => label.click());
  expect(h.setEnabled).toHaveBeenCalledTimes(1);
  expect(h.setEnabled).toHaveBeenLastCalledWith({ teamId: "demo", setTeamJoinLink: { enabled: true } });
  await act(async () => toggle().click());
  expect(h.setEnabled).toHaveBeenCalledTimes(2);
  expect(toggle().getAttribute("aria-labelledby")).toBe(label.id);
});
