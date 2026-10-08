// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
// @vitest-environment-options {"url":"http://localhost:5173"}
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const hooks = vi.hoisted(() => ({
  generate: vi.fn(),
  reveal: vi.fn(),
  revoke: vi.fn(),
  reset: vi.fn(),
  query: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("../../../../../common/config", () => ({ getConfig: () => ({ frontend_basename: "/" }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformEnrollmentLinksQuery: (...args: unknown[]) => {
    hooks.query(...args);
    return {
      data: {
        items: [
          {
            id: "invitation",
            note: "Workshop",
            created_at: "2026-10-01T12:00:00Z",
            expires_at: null,
            revoked_at: null,
            status: "active",
            opening_count: 7,
            last_opened_at: null,
            recoverable: true,
          },
        ],
        total: 1,
      },
      isFetching: false,
    };
  },
  useGeneratePlatformLinkMutation: () => [hooks.generate, { isLoading: false, reset: hooks.reset }],
  useRevealPlatformLinkMutation: () => [hooks.reveal, { isLoading: false, reset: hooks.reset }],
  useRevokePlatformLinkMutation: () => [hooks.revoke, { isLoading: false }],
}));
import PlatformAccessLinkManager from "./PlatformAccessLinkManager";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  vi.clearAllMocks();
  hooks.generate.mockReturnValue({ unwrap: async () => ({ token: "fixture-generated-token" }) });
  hooks.reveal.mockReturnValue({ unwrap: async () => ({ token: "fixture-original-token" }) });
  hooks.revoke.mockReturnValue({ unwrap: async () => undefined });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const render = (free = true) =>
  act(() =>
    root.render(
      <PlatformAccessLinkManager team={{ team_id: "demo", name: "Demo", allowed: false, free }} onClose={vi.fn()} />,
    ),
  );
const button = (key: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent?.trim() === `rework.platformAccess.${key}`,
  )!;
const input = (key: string) =>
  [...document.querySelectorAll<HTMLInputElement>("input")].find(
    (node) => node.labels?.[0]?.textContent === `rework.platformAccess.${key}`,
  )!;
const change = (node: HTMLInputElement, value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
it("keeps history available while Free is suspended and prevents link creation", () => {
  render(false);
  expect(document.body.textContent).toContain("Workshop");
  expect(document.body.textContent).toContain("7");
  expect(document.body.textContent).toContain("rework.platformAccess.links.suspendedHint");
  expect(button("createLink").disabled).toBe(true);
  expect(button("links.revoke").disabled).toBe(false);
});
it("creates a noted link without an implicit expiry and clears reusable mutation data", async () => {
  render();
  change(input("links.note"), "Demo workshop");
  await act(async () => button("createLink").click());
  expect(hooks.generate).toHaveBeenCalledWith({
    teamId: "demo",
    createPlatformEnrollmentLink: { note: "Demo workshop", expires_at: null },
  });
  expect(input("copyLink").value).toContain("/join-free/fixture-generated-token");
  expect(input("links.note").value).toBe("");
  expect(hooks.reset).toHaveBeenCalled();
});
it("recovers an existing URL without creating another invitation and confirms revocation", async () => {
  render();
  await act(async () => button("links.showUrl").click());
  expect(hooks.reveal).toHaveBeenCalledWith({ teamId: "demo", linkId: "invitation" });
  expect(hooks.generate).not.toHaveBeenCalled();
  expect(input("copyLink").value).toContain("/join-free/fixture-original-token");
  act(() => button("links.revoke").click());
  expect(hooks.revoke).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain("rework.platformAccess.links.revokeHint");
  await act(async () => button("links.revoke").click());
  expect(hooks.revoke).toHaveBeenCalledWith({ teamId: "demo", linkId: "invitation" });
  expect(input("copyLink")).toBeUndefined();
});
it("rejects a past local expiry before requesting a link and preserves the note", () => {
  render();
  change(input("links.note"), "Future demo");
  change(input("links.expiry"), "2020-01-01T12:00");
  expect(button("createLink").disabled).toBe(true);
  expect(document.body.textContent).toContain("rework.platformAccess.links.futureExpiry");
  expect(input("links.note").value).toBe("Future demo");
  expect(hooks.generate).not.toHaveBeenCalled();
});

it("keeps revocation failure visible inside the confirmation", async () => {
  hooks.revoke.mockReturnValue({
    unwrap: async () => {
      throw new Error("unavailable");
    },
  });
  render();
  act(() => button("links.revoke").click());
  await act(async () => button("links.revoke").click());
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.querySelector('[role="alert"]')?.textContent).toContain("rework.platformAccess.failed");
});
it("does not dismiss note or expiry drafts when Enter is pressed", () => {
  render();
  for (const key of ["links.note", "links.expiry"]) {
    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    act(() => input(key).dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
  }
});
