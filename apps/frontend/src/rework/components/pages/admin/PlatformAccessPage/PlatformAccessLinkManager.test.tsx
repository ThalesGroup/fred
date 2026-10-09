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
            last_opened_at: "2026-10-02T12:34:56Z",
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
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
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
    (node) =>
      node.getAttribute("aria-label") === `rework.platformAccess.${key}` ||
      (key === "links.copyUrl" && node.getAttribute("aria-label") === "rework.platformAccess.links.copied") ||
      node.textContent?.trim() === `rework.platformAccess.${key}`,
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
  expect(document.body.textContent).not.toContain(new Date("2026-10-02T12:34:56Z").toLocaleString("en"));
  expect(document.body.textContent).toContain("rework.platformAccess.links.suspendedHint");
  expect(button("createLink").disabled).toBe(true);
  expect(button("links.revoke").disabled).toBe(false);
});
it("creates a noted link without an implicit expiry and clears reusable mutation data", async () => {
  render();
  act(() => button("createLink").click());
  change(input("links.note"), "Demo workshop");
  await act(async () => button("createLink").click());
  expect(hooks.generate).toHaveBeenCalledWith({
    teamId: "demo",
    createPlatformEnrollmentLink: { note: "Demo workshop", expires_at: null },
  });
  expect(input("copyLink").value).toContain("/join-free/fixture-generated-token");
  expect(input("links.note")).toBeUndefined();
  expect(hooks.reset).toHaveBeenCalled();
});
it("recovers an existing URL without creating another invitation and confirms revocation", async () => {
  render();
  await act(async () => button("links.copyUrl").click());
  expect(hooks.reveal).toHaveBeenCalledWith({ teamId: "demo", linkId: "invitation" });
  expect(hooks.generate).not.toHaveBeenCalled();
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("http://localhost:5173/join-free/fixture-original-token");
  expect(document.body.textContent).toContain("rework.platformAccess.links.copied");
  expect(button("links.copyUrl").querySelector('[aria-hidden="true"]')?.textContent).toBe("check");
  expect(document.querySelector('[role="dialog"] p[role="status"]')).toBeNull();
  act(() => button("links.revoke").click());
  expect(hooks.revoke).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain("rework.platformAccess.links.revokeHint");
  await act(async () => button("links.revoke").click());
  expect(hooks.revoke).toHaveBeenCalledWith({ teamId: "demo", linkId: "invitation" });
  expect(input("copyLink")).toBeUndefined();
});
it("rejects a past local expiry before requesting a link and preserves the note", () => {
  render();
  act(() => button("createLink").click());
  change(input("links.note"), "Future demo");
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.getAttribute("aria-expanded") === "false")!
      .click(),
  );
  change(input("links.expiryDate"), "2020-01-01T12:00");
  expect(
    [...document.querySelectorAll<HTMLButtonElement>("button")].find(
      (node) => node.textContent === "rework.analytics.timeRange.apply",
    )!.disabled,
  ).toBe(true);
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
it("shows history first and returns without generation when creation is canceled", () => {
  render();
  expect(input("links.note")).toBeUndefined();
  act(() => button("createLink").click());
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.getAttribute("aria-expanded") === "false")!
      .click(),
  );
  expect(input("links.expiryDate").lang).toBe("en-GB");
  act(() => input("links.expiryDate").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(input("links.expiryDate")).toBeUndefined();
  expect(input("links.note")).toBeDefined();
  expect(button("createLink").disabled).toBe(false);
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.textContent === "common.cancel")!
      .click(),
  );
  expect(document.body.textContent).toContain("Workshop");
  expect(hooks.generate).not.toHaveBeenCalled();
});
it("retains an existing recovered URL when clipboard access fails without generating", async () => {
  vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error("permission"));
  render();
  await act(async () => button("links.copyUrl").click());
  expect(input("copyLink").value).toContain("/join-free/fixture-original-token");
  expect(document.body.textContent).toContain("rework.platformAccess.links.copyFailed");
  expect(document.body.textContent).not.toContain("rework.platformAccess.failed");
  expect(hooks.generate).not.toHaveBeenCalled();
  vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined);
  await act(async () => button("links.copyUrl").click());
  expect(document.body.textContent).toContain("rework.platformAccess.links.copied");
  expect(hooks.reveal).toHaveBeenCalledTimes(1);
});

it("applies a custom future expiration before creation and converts local time to UTC", async () => {
  render();
  act(() => button("createLink").click());
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.getAttribute("aria-expanded") === "false")!
      .click(),
  );
  change(input("links.expiryDate"), "2099-01-01T12:34");
  expect(button("createLink").disabled).toBe(true);
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.textContent === "rework.analytics.timeRange.apply")!
      .click(),
  );
  expect(input("links.expiryDate")).toBeUndefined();
  await act(async () => button("createLink").click());
  expect(hooks.generate).toHaveBeenCalledWith({
    teamId: "demo",
    createPlatformEnrollmentLink: { note: null, expires_at: new Date("2099-01-01T12:34").toISOString() },
  });
});
it("uses future duration shortcuts and can remove expiration without closing creation", () => {
  render();
  act(() => button("createLink").click());
  const open = () =>
    act(() =>
      [...document.querySelectorAll<HTMLButtonElement>("button")]
        .find((node) => node.getAttribute("aria-expanded") === "false")!
        .click(),
    );
  open();
  act(() => button("links.expiryPresets.days7").click());
  open();
  expect(new Date(input("links.expiryDate").value).getTime()).toBeGreaterThan(Date.now() + 6 * 86400000);
  act(() => button("links.never").click());
  expect(document.querySelector('[aria-expanded="false"]')?.textContent).toContain("rework.platformAccess.links.never");
  expect(button("createLink").disabled).toBe(false);
});

it("consumes Escape before the parent dialog even when focus has returned to the note", () => {
  render();
  act(() => button("createLink").click());
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.getAttribute("aria-expanded") === "false")!
      .click(),
  );
  act(() => {
    input("links.note").focus();
    input("links.note").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
  expect(input("links.expiryDate")).toBeUndefined();
  expect(input("links.note")).toBeDefined();
  expect(document.activeElement?.getAttribute("aria-expanded")).toBe("false");
});
