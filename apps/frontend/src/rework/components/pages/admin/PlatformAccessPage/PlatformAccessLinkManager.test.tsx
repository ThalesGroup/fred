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
  cleanup: vi.fn(),
  fetching: false,
  error: false,
  total: 1,
  inactive: 5,
  uncachedPage: false,
  linkStatus: "active",
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("../../../../../common/config", () => ({ getConfig: () => ({ frontend_basename: "/" }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformEnrollmentLinksQuery: (...args: unknown[]) => {
    hooks.query(...args);
    const data = {
      items: [
        {
          id: "invitation",
          note: "Workshop",
          created_at: "2026-10-01T12:00:00Z",
          expires_at: null,
          revoked_at: null,
          status: hooks.linkStatus,
          opening_count: 7,
          last_opened_at: "2026-10-02T12:34:56Z",
          recoverable: true,
        },
      ],
      total: hooks.total,
      inactive_count: hooks.inactive,
    };
    const uncached = hooks.uncachedPage && (args[0] as { offset: number }).offset > 0;
    return {
      data,
      currentData: uncached ? undefined : data,
      isFetching: hooks.fetching || uncached,
      isError: hooks.error,
    };
  },
  useGeneratePlatformLinkMutation: () => [hooks.generate, { isLoading: false, reset: hooks.reset }],
  useRevealPlatformLinkMutation: () => [hooks.reveal, { isLoading: false, reset: hooks.reset }],
  useRevokePlatformLinkMutation: () => [hooks.revoke, { isLoading: false }],
  useDeleteInactivePlatformLinksMutation: () => [hooks.cleanup, { isLoading: false }],
}));
import PlatformAccessLinkManager from "./PlatformAccessLinkManager";
import styles from "./PlatformAccessPage.module.css";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  vi.clearAllMocks();
  hooks.generate.mockReturnValue({ unwrap: async () => ({ token: "fixture-generated-token" }) });
  hooks.reveal.mockReturnValue({ unwrap: async () => ({ token: "fixture-original-token" }) });
  hooks.revoke.mockReturnValue({ unwrap: async () => undefined });
  hooks.cleanup.mockReturnValue({ unwrap: async () => ({ deleted_count: 5 }) });
  hooks.fetching = false;
  hooks.error = false;
  hooks.total = 1;
  hooks.inactive = 5;
  hooks.uncachedPage = false;
  hooks.linkStatus = "active";
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
const selectStatus = (status: string) => {
  act(() => document.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!.click());
  act(() => {
    [...document.querySelectorAll<HTMLElement>('[role="option"]')]
      .find((node) => node.textContent?.includes(`rework.platformAccess.links.status.${status}`))!
      .click();
  });
};

it("filters complete history from the first page", () => {
  hooks.total = 50;
  render();
  act(() => document.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ offset: 25, status: undefined });
  selectStatus("expired");
  expect(hooks.query.mock.lastCall?.[0]).toEqual({ teamId: "demo", offset: 0, limit: 25, status: "expired" });
});

it("keeps an uncached page selected while its first request is loading", () => {
  hooks.total = 50;
  hooks.uncachedPage = true;
  render();
  act(() => document.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  expect(document.body.textContent).not.toContain("Workshop");
  expect(button("links.cleanup").disabled).toBe(true);
  hooks.uncachedPage = false;
  render();
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  expect(document.body.textContent).toContain("Workshop");
});

it("hides stale rows during refresh without resetting the current page", () => {
  hooks.total = 50;
  render();
  act(() => document.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  hooks.fetching = true;
  render();
  expect(document.body.textContent).not.toContain("Workshop");
  expect(button("links.cleanup").disabled).toBe(true);
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  hooks.fetching = false;
  hooks.error = true;
  render();
  expect(document.body.textContent).not.toContain("Workshop");
});

it("requires cleanup confirmation and preserves the selected filter", async () => {
  render(false);
  selectStatus("revoked");
  act(() => button("links.cleanup").click());
  expect(hooks.cleanup).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain("rework.platformAccess.links.cleanupHint");
  expect(document.querySelector('[inert] [role="dialog"]')?.textContent).toContain("Workshop");
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.textContent === "common.cancel")!
      .click(),
  );
  expect(hooks.cleanup).not.toHaveBeenCalled();
  act(() => button("links.cleanup").click());
  await act(async () => button("links.cleanupConfirm").click());
  expect(hooks.cleanup).toHaveBeenCalledWith({ teamId: "demo" });
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ status: "revoked", offset: 0 });
  expect(document.body.textContent).toContain("rework.platformAccess.links.deleted");
});

it("keeps a failed cleanup in the confirmation without claiming success", async () => {
  hooks.cleanup.mockReturnValue({
    unwrap: async () => {
      throw new Error("unavailable");
    },
  });
  render();
  act(() => button("links.cleanup").click());
  await act(async () => button("links.cleanupConfirm").click());
  expect(document.querySelector('[role="dialog"] [role="alert"]')?.textContent).toContain(
    "rework.platformAccess.failed",
  );
  expect(document.body.textContent).not.toContain("rework.platformAccess.links.deleted");
});

it("disables cleanup without obsolete links", () => {
  hooks.inactive = 0;
  render();
  expect(button("links.cleanup").disabled).toBe(true);
});
it("keeps history available while Free is suspended and prevents link creation", () => {
  hooks.linkStatus = "suspended";
  render(false);
  expect(document.body.textContent).toContain("Workshop");
  expect(document.body.textContent).toContain("7");
  expect(document.body.textContent).not.toContain(new Date("2026-10-02T12:34:56Z").toLocaleString("en"));
  expect(document.body.textContent).not.toContain("rework.platformAccess.links.suspendedHint");
  expect(document.querySelector(`.${styles.suspendedLink} .${styles.screenReaderOnly}`)?.textContent).toBe(
    "rework.platformAccess.links.status.suspended",
  );
  expect(button("createLink").disabled).toBe(true);
  expect(button("links.revoke").disabled).toBe(false);
  expect(button("links.copyUrl").disabled).toBe(false);
  expect(document.querySelector(`.${styles.suspendedLink}`)?.textContent).toContain("Workshop");
  act(() => document.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!.click());
  expect([...document.querySelectorAll('[role="option"]')].map((option) => option.textContent)).toEqual(
    ["all", "active", "revoked", "expired"].map((status) => `rework.platformAccess.links.status.${status}`),
  );
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
