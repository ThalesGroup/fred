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
  revealLoading: false,
  query: vi.fn(),
  linkRefetch: vi.fn(),
  linkOpeningCount: 7,
  joinerQuery: vi.fn(),
  joinerRefetch: vi.fn(),
  joinerFetching: false,
  joinerUncachedPage: false,
  joinerError: false,
  joinerTotal: 1,
  joinerDeleted: false,
  cleanup: vi.fn(),
  fetching: false,
  error: false,
  total: 1,
  inactive: 5,
  uncachedPage: false,
  uncachedFilter: false,
  linkStatus: "active",
  linkNote: "Workshop" as string | null,
  teamFree: undefined as boolean | undefined,
  teamQuery: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("../../../../../common/config", () => ({ getConfig: () => ({ frontend_basename: "/" }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessTeamsQuery: (...args: unknown[]) => {
    hooks.teamQuery(...args);
    return { data: hooks.teamFree === undefined ? undefined : [{ team_id: "demo", free: hooks.teamFree }] };
  },
  usePlatformEnrollmentLinksQuery: (...args: unknown[]) => {
    hooks.query(...args);
    const data = {
      items: [
        {
          id: "invitation",
          note: hooks.linkNote,
          created_at: "2026-10-01T12:00:00Z",
          expires_at: null,
          revoked_at: null,
          status: hooks.linkStatus,
          opening_count: hooks.linkOpeningCount,
          last_opened_at: "2026-10-02T12:34:56Z",
          recoverable: true,
        },
      ],
      total: hooks.total,
      inactive_count: hooks.inactive,
    };
    const query = args[0] as { offset: number; status?: string };
    const uncached = (hooks.uncachedPage && query.offset > 0) || (hooks.uncachedFilter && !!query.status);
    return {
      data,
      currentData: uncached ? undefined : data,
      isFetching: hooks.fetching || uncached,
      isError: hooks.error,
      refetch: hooks.linkRefetch,
    };
  },
  usePlatformEnrollmentJoinersQuery: (...args: unknown[]) => {
    hooks.joinerQuery(...args);
    const uncached = hooks.joinerUncachedPage && (args[0] as { offset: number }).offset > 0;
    return {
      currentData: uncached
        ? undefined
        : {
            items: [
              {
                user_id: "joined-user",
                username: "simon",
                first_name: "Simon",
                last_name: "Martin",
                joined_at: "2026-10-12T12:00:00Z",
                deleted: hooks.joinerDeleted,
              },
            ],
            total: hooks.joinerTotal,
          },
      isFetching: hooks.joinerFetching || uncached,
      isError: hooks.joinerError,
      refetch: hooks.joinerRefetch,
    };
  },
  useGeneratePlatformLinkMutation: () => [hooks.generate, { isLoading: false, reset: hooks.reset }],
  useRevealPlatformLinkMutation: () => [hooks.reveal, { isLoading: hooks.revealLoading, reset: hooks.reset }],
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
  hooks.uncachedFilter = false;
  hooks.linkStatus = "active";
  hooks.linkOpeningCount = 7;
  hooks.linkNote = "Workshop";
  hooks.teamFree = undefined;
  hooks.joinerFetching = false;
  hooks.joinerUncachedPage = false;
  hooks.joinerError = false;
  hooks.joinerTotal = 1;
  hooks.joinerDeleted = false;
  hooks.revealLoading = false;
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
      !node.closest("[inert]") &&
      (node.getAttribute("aria-label") === `rework.platformAccess.${key}` ||
        (key === "links.copyUrl" && node.getAttribute("aria-label") === "rework.platformAccess.links.copied") ||
        node.textContent?.trim() === `rework.platformAccess.${key}`),
  )!;
const frontDialog = () => {
  const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"]');
  return dialogs[dialogs.length - 1]!;
};
const frontConfirmButton = () => {
  const buttons = frontDialog().querySelectorAll<HTMLButtonElement>("button");
  return buttons[buttons.length - 1]!;
};
const collapsedExpiry = () => frontDialog().querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!;
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
  expect(hooks.query.mock.lastCall?.[1]).toEqual({ refetchOnMountOrArgChange: true });
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
  expect(document.querySelector('[role="status"][aria-label="rework.platformAccess.links.loading"]')).not.toBeNull();
  hooks.uncachedPage = false;
  render();
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  expect(document.body.textContent).toContain("Workshop");
});

it("does not show rows from another filter while a new filter is loading", () => {
  hooks.uncachedFilter = true;
  render();
  selectStatus("expired");
  expect(hooks.query.mock.lastCall?.[0]).toMatchObject({ status: "expired", offset: 0 });
  expect(document.body.textContent).not.toContain("Workshop");
  expect(button("links.cleanup").disabled).toBe(true);
  expect(document.querySelector('[role="status"][aria-label="rework.platformAccess.links.loading"]')).not.toBeNull();
});

it("keeps cached links and actions visible during background refresh", () => {
  hooks.total = 50;
  render();
  act(() => document.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  hooks.fetching = true;
  render();
  expect(document.body.textContent).toContain("Workshop");
  expect(button("links.cleanup").disabled).toBe(false);
  expect(button("links.copyUrl").disabled).toBe(false);
  expect(button("links.joiners").disabled).toBe(false);
  expect(button("links.revoke").disabled).toBe(false);
  expect(document.querySelector('[role="status"][aria-label="rework.platformAccess.links.loading"]')).toBeNull();
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

it("keeps cleanup in the dialog footer, away from the status filter", () => {
  render();
  const filter = document.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!;
  const cleanup = button("links.cleanup");
  expect(filter.parentElement?.closest(`.${styles.linkControls}`)?.contains(cleanup)).toBe(false);
  expect(cleanup.compareDocumentPosition(button("createLink")) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  expect(document.querySelector(`.${styles.linkControls}`)?.contains(button("createLink"))).toBe(true);
});
it("keeps history available while Free is suspended and prevents link creation", () => {
  hooks.linkStatus = "suspended";
  render(false);
  expect(document.body.textContent).toContain("Workshop");
  expect(document.body.textContent).toContain("7");
  expect(document.body.textContent).not.toContain(new Date("2026-10-02T12:34:56Z").toLocaleString("en"));
  expect(document.querySelector(`.${styles.linkSuspendedNotice}`)?.textContent).toContain(
    "rework.platformAccess.links.suspendedHint",
  );
  expect(document.querySelector(`.${styles.suspendedLink}`)?.textContent).toContain(
    "rework.platformAccess.links.status.suspended",
  );
  expect(document.querySelector(`.${styles.suspendedLink} .${styles.screenReaderOnly}`)).toBeNull();
  expect(button("createLink").disabled).toBe(true);
  expect(button("links.revoke").disabled).toBe(false);
  expect(button("links.copyUrl").disabled).toBe(false);
  expect(document.querySelector(`.${styles.suspendedLink}`)?.textContent).toContain("Workshop");
  act(() => document.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!.click());
  expect([...document.querySelectorAll('[role="option"]')].map((option) => option.textContent)).toEqual(
    ["all", "active", "revoked", "expired"].map((status) => `rework.platformAccess.links.status.${status}`),
  );
});

it("refreshes the link access setting when the manager opens", () => {
  render();
  expect(hooks.teamQuery).toHaveBeenCalledWith(undefined, { refetchOnMountOrArgChange: true });
  expect(document.querySelector(`.${styles.linkSuspendedNotice}`)).toBeNull();
  hooks.teamFree = false;
  hooks.linkStatus = "suspended";
  act(() => root.render(null));
  render();
  expect(document.querySelector(`.${styles.linkSuspendedNotice}`)).not.toBeNull();
  expect(button("createLink").disabled).toBe(true);
  hooks.teamFree = true;
  hooks.linkStatus = "active";
  render();
  expect(document.querySelector(`.${styles.linkSuspendedNotice}`)).toBeNull();
  expect(button("createLink").disabled).toBe(false);
});

it("keeps link actions and dialog controls available during URL reveal", () => {
  hooks.revealLoading = true;
  render();
  expect(button("createLink").disabled).toBe(false);
  expect(
    [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === "common.close")
      ?.disabled,
  ).toBe(false);
  expect(button("links.copyUrl").disabled).toBe(false);
  expect(button("links.joiners").disabled).toBe(false);
  expect(button("links.revoke").disabled).toBe(false);
});

it("leaves an absent note blank and gives its joiners a generic title", () => {
  hooks.linkNote = null;
  render();
  expect(document.querySelector(`.${styles.linkSuspendedNotice}`)).toBeNull();
  expect(document.querySelector(`.${styles.exampleValue}`)?.textContent).toBe("");
  act(() => button("links.joiners").click());
  expect(frontDialog().querySelector("p")?.textContent).toBe("rework.platformAccess.links.joiners");
});

it("shows successful joiners on a revoked link with bounded pages", () => {
  hooks.linkStatus = "revoked";
  hooks.joinerTotal = 26;
  render(false);
  expect(document.querySelector<HTMLElement>(`.${styles.boundedTable}`)?.getAttribute("style")).toBeNull();
  expect(
    [...document.querySelectorAll<HTMLButtonElement>(`.${styles.linkActions} button`)].map((node) =>
      node.getAttribute("aria-label"),
    ),
  ).toEqual([
    "rework.platformAccess.links.copyUrl",
    "rework.platformAccess.links.joiners",
    "rework.platformAccess.links.revoke",
  ]);
  act(() => button("links.joiners").click());
  expect(frontDialog().querySelector("p")?.textContent).toBe("rework.platformAccess.links.joinersTitle");
  expect(hooks.joinerQuery.mock.lastCall?.[0]).toMatchObject({
    teamId: "demo",
    linkId: "invitation",
    offset: 0,
    limit: 25,
  });
  expect(hooks.joinerQuery.mock.lastCall?.[1]).toEqual({ skip: false, refetchOnMountOrArgChange: true });
  expect(document.body.textContent).toContain("simon");
  expect(document.body.textContent).toContain("Martin");
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2);
  expect(document.querySelector('[inert] [role="dialog"]')?.textContent).toContain("Workshop");
  expect(document.querySelector('[inert] [role="dialog"]')?.closest('[aria-hidden="true"]')).not.toBeNull();
  const nextButtons = document.querySelectorAll<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]');
  act(() => nextButtons[nextButtons.length - 1]!.click());
  expect(hooks.joinerQuery.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  act(() =>
    [...document.querySelectorAll<HTMLButtonElement>("button")]
      .find((node) => node.textContent === "rework.back")!
      .click(),
  );
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1);
  expect(document.querySelector('[inert] [role="dialog"]')).toBeNull();
  expect(document.body.textContent).toContain("Workshop");
});

it("keeps the last known identity visible on a dimmed deleted joiner", () => {
  hooks.joinerDeleted = true;
  render();
  act(() => button("links.joiners").click());
  const row = document.querySelector(`.${styles.deletedJoiner}`);
  expect(row?.textContent).toContain("simon(rework.platformAccess.links.deletedUser)");
  expect(row?.textContent).toContain("Simon");
  expect(row?.textContent).toContain("Martin");
  expect(row?.querySelector(`.${styles.joinerUsernameText}`)?.getAttribute("title")).toBe("simon");
});

it("keeps cached joiners visible during refresh and handles errors and empty results", () => {
  render();
  act(() => button("links.joiners").click());
  hooks.joinerFetching = true;
  render();
  expect(document.body.textContent).toContain("simon");
  expect(frontDialog().querySelector('[role="status"][aria-label="rework.platformAccess.links.loading"]')).toBeNull();
  hooks.joinerFetching = false;
  hooks.joinerError = true;
  render();
  expect(document.body.textContent).toContain("rework.platformAccess.links.joinersFailed");
  act(() => button("retry").click());
  expect(hooks.joinerRefetch).toHaveBeenCalled();
  hooks.joinerError = false;
  hooks.joinerTotal = 0;
  render();
  expect(document.body.textContent).toContain("rework.platformAccess.links.noJoiners");
});

it("refreshes joined users and the underlying opening count on demand", () => {
  render();
  act(() => button("links.joiners").click());
  const refresh = frontDialog().querySelector<HTMLButtonElement>('button[aria-label="common.refresh"]')!;
  expect(refresh.title).toBe("common.refresh");
  expect(refresh.textContent).toBe("refresh");
  expect(document.querySelector(`.${styles.boundedTable} [title="7"]`)).not.toBeNull();
  act(() => refresh.click());
  expect(hooks.joinerRefetch).toHaveBeenCalledOnce();
  expect(hooks.linkRefetch).toHaveBeenCalledOnce();
  hooks.joinerFetching = true;
  hooks.fetching = true;
  render();
  expect(frontDialog().textContent).toContain("simon");
  expect(document.querySelector(`.${styles.boundedTable} [title="7"]`)).not.toBeNull();
  expect(refresh.disabled).toBe(true);
  expect(refresh.getAttribute("aria-busy")).toBe("true");
  hooks.joinerFetching = false;
  hooks.fetching = false;
  hooks.linkOpeningCount = 8;
  render();
  expect(document.querySelector(`.${styles.boundedTable} [title="8"]`)).not.toBeNull();
  expect(refresh.disabled).toBe(false);
});

it("shows loading instead of a previous joiner page when pagination is uncached", () => {
  hooks.joinerTotal = 26;
  hooks.joinerUncachedPage = true;
  render();
  act(() => button("links.joiners").click());
  const nextButtons = frontDialog().querySelectorAll<HTMLButtonElement>(
    'button[aria-label="dataTable.pagination.next"]',
  );
  act(() => nextButtons[nextButtons.length - 1]!.click());
  expect(hooks.joinerQuery.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  expect(frontDialog().textContent).not.toContain("simon");
  expect(
    frontDialog().querySelector('[role="status"][aria-label="rework.platformAccess.links.loading"]'),
  ).not.toBeNull();
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
  expect(input("copyLink").value).toContain("/join/fixture-generated-token");
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("http://localhost:5173/join/fixture-generated-token");
  expect(button("links.copyUrl").querySelector('[aria-hidden="true"]')?.textContent).toBe("check");
  expect(input("links.note")).toBeUndefined();
  expect(hooks.reset).toHaveBeenCalled();
});
it("keeps a generated URL available when automatic clipboard writing fails", async () => {
  vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error("permission"));
  render();
  act(() => button("createLink").click());
  await act(async () => button("createLink").click());
  expect(input("copyLink").value).toContain("/join/fixture-generated-token");
  expect(document.body.textContent).toContain("rework.platformAccess.links.copyFailed");
  expect(document.body.textContent).not.toContain("rework.platformAccess.failed");
  expect(hooks.generate).toHaveBeenCalledTimes(1);
  await act(async () => button("links.copyUrl").click());
  expect(button("links.copyUrl").querySelector('[aria-hidden="true"]')?.textContent).toBe("check");
  expect(hooks.generate).toHaveBeenCalledTimes(1);
});
it("does not reopen a dismissed result after a delayed clipboard rejection", async () => {
  let rejectCopy!: (error: Error) => void;
  vi.mocked(navigator.clipboard.writeText).mockImplementationOnce(
    () => new Promise<void>((_, reject) => (rejectCopy = reject)),
  );
  render();
  act(() => button("createLink").click());
  await act(async () => button("createLink").click());
  act(() => frontConfirmButton().click());
  expect(input("copyLink")).toBeUndefined();
  await act(async () => rejectCopy(new Error("permission")));
  expect(input("copyLink")).toBeUndefined();
  expect(document.body.textContent).not.toContain("rework.platformAccess.links.copyFailed");
});
it("ignores an older automatic copy result after a manual retry", async () => {
  let rejectCopy!: (error: Error) => void;
  vi.mocked(navigator.clipboard.writeText).mockImplementationOnce(
    () => new Promise<void>((_, reject) => (rejectCopy = reject)),
  );
  render();
  act(() => button("createLink").click());
  await act(async () => button("createLink").click());
  await act(async () => button("links.copyUrl").click());
  await act(async () => rejectCopy(new Error("permission")));
  expect(button("links.copyUrl").querySelector('[aria-hidden="true"]')?.textContent).toBe("check");
  expect(document.body.textContent).not.toContain("rework.platformAccess.links.copyFailed");
});
it("recovers an existing URL without creating another invitation and confirms revocation", async () => {
  render();
  await act(async () => button("links.copyUrl").click());
  expect(hooks.reveal).toHaveBeenCalledWith({ teamId: "demo", linkId: "invitation" });
  expect(hooks.generate).not.toHaveBeenCalled();
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("http://localhost:5173/join/fixture-original-token");
  expect(document.body.textContent).toContain("rework.platformAccess.links.copied");
  expect(button("links.copyUrl").querySelector('[aria-hidden="true"]')?.textContent).toBe("check");
  expect(document.querySelector('[role="dialog"] p[role="status"]')).toBeNull();
  act(() => button("links.revoke").click());
  expect(hooks.revoke).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain("rework.platformAccess.links.revokeHint");
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2);
  expect(document.querySelector('[inert] [role="dialog"]')?.textContent).toContain("Workshop");
  await act(async () => frontConfirmButton().click());
  expect(hooks.revoke).toHaveBeenCalledWith({ teamId: "demo", linkId: "invitation" });
  expect(input("copyLink")).toBeUndefined();
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1);
});
it("rejects a past local expiry before requesting a link and preserves the note", () => {
  render();
  act(() => button("createLink").click());
  change(input("links.note"), "Future demo");
  act(() => collapsedExpiry().click());
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
  await act(async () => frontConfirmButton().click());
  const dialog = frontDialog();
  expect(dialog.querySelector('[role="alert"]')?.textContent).toContain("rework.platformAccess.failed");
});
it("shows history first and returns without generation when creation is canceled", () => {
  render();
  expect(input("links.note")).toBeUndefined();
  act(() => button("createLink").click());
  act(() => collapsedExpiry().click());
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
it("keeps the links and create dialog mounted while showing a generated URL", async () => {
  render();
  const linksDialog = frontDialog();
  const createTrigger = button("createLink");
  act(() => {
    createTrigger.focus();
    createTrigger.click();
  });
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2);
  expect(document.querySelector('[inert] [role="dialog"]')).toBe(linksDialog);
  const createDialog = frontDialog();
  const createWidth = createDialog.style.width;
  await act(async () => button("createLink").click());
  expect(frontDialog()).toBe(createDialog);
  expect(frontDialog().style.width).toBe(createWidth);
  expect(document.querySelector('[inert] [role="dialog"]')).toBe(linksDialog);
  expect(document.activeElement).toBe(input("copyLink"));
  expect(input("copyLink").selectionStart).toBe(0);
  expect(input("copyLink").selectionEnd).toBe(input("copyLink").value.length);
  expect(input("copyLink").selectionDirection).toBe("backward");
  expect(input("copyLink").scrollLeft).toBe(0);
  act(() => frontConfirmButton().click());
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1);
  expect(frontDialog()).toBe(linksDialog);
  expect(document.activeElement).toBe(createTrigger);
});
it("retains an existing recovered URL when clipboard access fails without generating", async () => {
  vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error("permission"));
  render();
  await act(async () => button("links.copyUrl").click());
  expect(input("copyLink").value).toContain("/join/fixture-original-token");
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
  act(() => collapsedExpiry().click());
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
  const open = () => act(() => collapsedExpiry().click());
  open();
  act(() => button("links.expiryPresets.days7").click());
  open();
  expect(new Date(input("links.expiryDate").value).getTime()).toBeGreaterThan(Date.now() + 6 * 86400000);
  act(() => button("links.never").click());
  expect(collapsedExpiry().textContent).toContain("rework.platformAccess.links.never");
  expect(button("createLink").disabled).toBe(false);
});

it("consumes Escape before the parent dialog even when focus has returned to the note", () => {
  render();
  act(() => button("createLink").click());
  act(() => collapsedExpiry().click());
  act(() => {
    input("links.note").focus();
    input("links.note").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
  expect(input("links.expiryDate")).toBeUndefined();
  expect(input("links.note")).toBeDefined();
  expect(document.activeElement?.getAttribute("aria-expanded")).toBe("false");
});
