// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, useState } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import type {
  PlatformAccessActivationUser,
  PlatformAccessTeam,
  PlatformAccessUser,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const state = vi.hoisted(() => ({
  users: [
    {
      user_id: "user",
      username: "Alice",
      email: "alice@example.org",
      sources: [{ kind: "free", team_id: "demo", team_name: "Demo" }],
    },
  ] as PlatformAccessUser[],
  searchUsers: vi.fn(),
  teamQueries: vi.fn(),
  translated: vi.fn(),
  importQueries: vi.fn(),
  teams: [{ team_id: "demo", name: "Demo", allowed: false, free: true }] as PlatformAccessTeam[],
  picked: ["first", "second"] as string[],
  usersTotal: undefined as number | undefined,
  success: vi.fn(),
  revoke: vi.fn(() => ({ unwrap: async () => undefined })),
  usersFetching: false,
  usersError: false,
  completed: false,
  filteringEnabled: false,
  importFetching: false,
  importError: false,
  importMissing: false,
  previewRevision: 1,
  authorityRevision: 1,
  authorityError: false,
  authorityFetching: false,
  refreshAuthority: vi.fn(),
  previewUsers: [] as PlatformAccessActivationUser[],
  refreshPreview: vi.fn(),
  previewFetching: false,
  previewError: false,
  retryImport: vi.fn(),
  configured: true,
  filter: vi.fn(() => ({ unwrap: async () => undefined })),
  bulk: vi.fn((_arg: { grantPlatformAccessUsers: { user_ids: string[] } }) => ({ unwrap: async () => undefined })),
  importT0: vi.fn(() => ({ unwrap: async () => undefined })),
  setTeam: vi.fn(() => ({ unwrap: async () => undefined })),
  refetchUsers: vi.fn(),
  refetchPending: vi.fn(),
  pending: [] as { email: string; granted_by: string; granted_at: string }[],
  countQueries: vi.fn(),
  pickedEmails: [] as string[],
  revokeUsers: vi.fn((_arg: unknown) => ({ unwrap: async () => ({ removed_count: 2 }) })),
  addEmail: vi.fn((_arg: unknown) => ({ unwrap: async () => undefined })),
  removeEmail: vi.fn((_arg: unknown) => ({ unwrap: async () => ({ removed_count: 1 }) })),
}));
// Keys only, plus the team names a string is given so grouped lines can be told apart.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { teams?: string }) => {
      state.translated(key, options);
      return options?.teams ? `${key}[${options.teams}]` : key;
    },
    i18n: { language: "en" },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: state.success }),
}));
vi.mock("../../../../../common/config", () => ({ getConfig: () => ({ platform_access_enabled: true }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessStateQuery: () => ({
    refetch: state.refreshAuthority,
    isError: state.authorityError,
    isFetching: state.authorityFetching,
    data: {
      filtering_enabled: state.filteringEnabled,
      revision: state.authorityRevision,
      has_admission_sources: state.configured,
    },
  }),
  usePlatformAccessActivationPreviewQuery: () => ({
    refetch: state.refreshPreview,
    isFetching: state.previewFetching,
    isError: state.previewError,
    data: {
      revision: state.previewRevision,
      allowed: state.previewUsers.length ? state.previewUsers.filter((u) => u.outcome === "allowed").length : 1,
      blocked: state.previewUsers.filter((u) => u.outcome === "blocked").length,
      unknown: state.previewUsers.filter((u) => u.outcome === "unknown").length,
      checked_at: "2026-10-08T12:00:00Z",
      users: state.previewUsers,
    },
  }),
  usePlatformAccessUsersQuery: (args: unknown, options: unknown) => {
    state.searchUsers(args, options);
    // As RTK Query does: nothing while skipped, and no current data while another page or search loads.
    if ((options as { skip: boolean }).skip) return { isFetching: false, isError: false, refetch: state.refetchUsers };
    return {
      refetch: state.refetchUsers,
      isFetching: state.usersFetching,
      isError: state.usersError,
      data: { total: 1, items: [{ user_id: "old", username: "Previous search", sources: [] }] },
      currentData: state.usersFetching
        ? undefined
        : { total: state.usersTotal ?? state.users.length, items: state.users },
    };
  },
  usePlatformAccessT0Query: (_args: unknown, options: { skip: boolean }) => {
    state.importQueries(options);
    return {
      isFetching: state.importFetching,
      isError: state.importError,
      refetch: state.retryImport,
      data: state.importMissing
        ? undefined
        : { candidates: 1, matching: 0, completed_at: state.completed ? "2026-01-01" : null },
    };
  },
  usePlatformAccessTeamsQuery: (_args: unknown, options: { skip: boolean }) => {
    state.teamQueries(options);
    return options.skip ? {} : { data: state.teams };
  },
  useSetPlatformFilteringMutation: () => [state.filter],
  useGrantPlatformUsersMutation: () => [state.bulk],
  useRevokePlatformUserMutation: () => [state.revoke],
  useRevokePlatformUsersMutation: () => [state.revokeUsers],
  usePlatformAccessPendingEmailsQuery: (_args: unknown, options: { skip: boolean }) =>
    options.skip ? { refetch: state.refetchPending } : { data: state.pending, refetch: state.refetchPending },
  usePlatformAccessOverlapCountsQuery: (args: unknown, options: { skip: boolean }) => {
    state.countQueries(args, options);
    return options.skip ? {} : { currentData: { rule: 4, whitelist_only: 7, unknown: 2 } };
  },
  useAddPlatformPendingEmailMutation: () => [state.addEmail],
  useRemovePlatformPendingEmailsMutation: () => [state.removeEmail],
  useImportPlatformT0Mutation: () => [state.importT0],
  useSetPlatformTeamMutation: () => [state.setTeam],
  useGeneratePlatformLinkMutation: () => [vi.fn()],
}));
vi.mock("./PlatformAccessRuleEditor", () => ({
  default: function RuleEditor() {
    const [draft, setDraft] = useState("Rule editor");
    return (
      <div>
        <span>{draft}</span>
        <button type="button" onClick={() => setDraft("Unsaved rule")}>
          Edit draft
        </button>
      </div>
    );
  },
}));
vi.mock("./PlatformAccessAddUsersDialog", () => ({
  default: ({
    open,
    busy,
    onClose,
    onConfirm,
  }: {
    open: boolean;
    busy: boolean;
    onClose: () => void;
    onConfirm: (ids: string[], emails: string[]) => void;
  }) =>
    open ? (
      <div data-testid="add-users-dialog" data-busy={busy}>
        <button type="button" onClick={() => onConfirm(state.picked, state.pickedEmails)}>
          Confirm selection
        </button>
        <button type="button" onClick={onClose}>
          Close dialog
        </button>
      </div>
    ) : null,
}));
import PlatformAccessPage from "./PlatformAccessPage";
import styles from "./PlatformAccessPage.module.css";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  state.teams = [{ team_id: "demo", name: "Demo", allowed: false, free: true }];
  state.picked = ["first", "second"];
  state.users = [
    {
      user_id: "user",
      username: "Alice",
      email: "alice@example.org",
      sources: [{ kind: "free", team_id: "demo", team_name: "Demo" }],
    },
  ];
  state.completed = false;
  state.usersTotal = undefined;
  state.usersFetching = false;
  state.usersError = false;
  state.filteringEnabled = false;
  state.importFetching = false;
  state.importError = false;
  state.importMissing = false;
  state.previewUsers = [];
  state.previewRevision = 1;
  state.authorityRevision = 1;
  state.authorityError = false;
  state.authorityFetching = false;
  state.previewFetching = false;
  state.previewError = false;
  state.configured = true;
  state.pending = [];
  state.pickedEmails = [];
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
});
const openTab = (tab: string) =>
  act(() =>
    [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
      .find((node) => node.textContent === `rework.platformAccess.tabs.${tab}`)!
      .click(),
  );
const visiblePanels = () =>
  [...host.querySelectorAll<HTMLElement>('[role="tabpanel"]')].filter((p) => !p.closest("[hidden]"));
const search = (value: string) => {
  const input = host.querySelector<HTMLInputElement>('[id$="-users-panel"] input[type="text"]')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  act(() => vi.advanceTimersByTime(300));
};
const type = (value: string) => {
  const input = host.querySelector<HTMLInputElement>('[id$="-users-panel"] input[type="text"]')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
};
const pageButton = (key: string) =>
  [...host.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === key)!;
// The add button carries an icon, so its text is more than its label.
const addUsersButton = () =>
  [...host.querySelectorAll<HTMLButtonElement>("button")].find((node) =>
    node.textContent?.includes("rework.platformAccess.addUsers"),
  )!;
const render = (query = "Al") => {
  act(() => root.render(<PlatformAccessPage />));
  openTab("users");
  search(query);
};

it("lists individual exceptions without a search and requests them only while the users sub-tab is shown", () => {
  act(() => root.render(<PlatformAccessPage />));
  expect(state.searchUsers.mock.calls.every(([, options]) => options.skip)).toBe(true);
  openTab("users");
  expect(state.searchUsers.mock.lastCall).toEqual([
    { offset: 0, limit: 20, query: "", exceptionsOnly: true },
    { skip: false },
  ]);
  expect(host.textContent).toContain("Alice");
  expect(host.textContent).not.toContain("Previous search");
  openTab("teams");
  expect(state.searchUsers.mock.lastCall?.[1]).toEqual({ skip: true });
  openTab("users");
  expect(state.searchUsers.mock.lastCall?.[1]).toEqual({ skip: false });
  openTab("rules");
  expect(state.searchUsers.mock.lastCall?.[1]).toEqual({ skip: true });
});

it("requests the teams listing and the import preview only for the tab that shows them", () => {
  act(() => root.render(<PlatformAccessPage />));
  const skipped = (query: typeof state.teamQueries) => query.mock.lastCall?.[0].skip;
  expect(state.teamQueries.mock.calls.every(([options]) => options.skip)).toBe(true);
  expect(state.importQueries.mock.calls.every(([options]) => options.skip)).toBe(true);
  openTab("users");
  expect([skipped(state.teamQueries), skipped(state.importQueries)]).toEqual([true, false]);
  openTab("teams");
  expect([skipped(state.teamQueries), skipped(state.importQueries)]).toEqual([false, true]);
  expect(host.querySelector('[id$="-teams-panel"]')?.textContent).toContain("Demo");
  openTab("rules");
  expect([skipped(state.teamQueries), skipped(state.importQueries)]).toEqual([true, true]);
});

it("waits for a pause in typing, trims the search and restarts at the first page", () => {
  state.usersTotal = 60;
  render("");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 20, limit: 20, query: "", exceptionsOnly: true });
  type(" A");
  type(" Al ");
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 20, limit: 20, query: "", exceptionsOnly: true });
  act(() => vi.advanceTimersByTime(300));
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 0, limit: 20, query: "Al", exceptionsOnly: true });
  expect(state.searchUsers.mock.calls.some(([args]) => args.query === "A")).toBe(false);
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  search("");
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 0, limit: 20, query: "", exceptionsOnly: true });
});

it("tells an empty whitelist apart from a search without match", () => {
  state.users = [];
  render("");
  const panel = host.querySelector<HTMLElement>('[id$="-users-panel"]')!;
  expect(panel.textContent).toContain("rework.platformAccess.emptyWhitelist");
  expect(addUsersButton().disabled).toBe(false);
  expect(panel.querySelector('input[type="text"]')).not.toBeNull();
  search("zz");
  expect(panel.textContent).toContain("rework.platformAccess.noUsers");
  expect(panel.textContent).not.toContain("rework.platformAccess.emptyWhitelist");
});

const usersPanel = () => host.querySelector<HTMLElement>('[id$="-users-panel"]')!;
const checkboxes = () => [...usersPanel().querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
const lastUsersQuery = () => state.searchUsers.mock.lastCall![0] as Record<string, unknown>;
const chip = (key: string) =>
  [...usersPanel().querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent?.includes(key))!;
const twoUsers = () => {
  state.users = [
    { user_id: "a", username: "Alice", email: null, sources: [{ kind: "manual" }] },
    { user_id: "b", username: "Bob", email: null, sources: [{ kind: "manual" }] },
  ];
  state.usersTotal = 240;
};

it("starts each row with a checkbox and keeps the per-row removal", () => {
  render("");
  // Header plus one per row.
  expect(checkboxes()).toHaveLength(2);
  expect(pageButton("rework.platformAccess.remove")).toBeDefined();
  expect(host.textContent).not.toContain("rework.platformAccess.selection.count");
});

it("selects every matching row across pages from the header, then removes all but the unchecked one", async () => {
  twoUsers();
  render("");
  act(() => checkboxes()[0].click());
  expect(checkboxes().every((box) => box.checked)).toBe(true);
  act(() => checkboxes()[2].click());
  expect(checkboxes()[0].indeterminate).toBe(true);
  act(() => chip("rework.platformAccess.selection.remove").click());
  const confirm = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent === "rework.platformAccess.bulkRemove.confirm",
  )!;
  await act(async () => confirm.click());
  expect(state.revokeUsers).toHaveBeenCalledWith({
    revokePlatformAccessUsers: { all_matching: true, query: "", overlap: null, excluded_ids: ["b"] },
  });
  expect(state.success).toHaveBeenCalledWith({ summary: "rework.platformAccess.bulkRemove.done" });
  expect(checkboxes().some((box) => box.checked)).toBe(false);
});

it("removes only the rows checked one by one", async () => {
  twoUsers();
  render("");
  act(() => checkboxes()[1].click());
  act(() => chip("rework.platformAccess.selection.remove").click());
  const confirm = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent === "rework.platformAccess.bulkRemove.confirm",
  )!;
  await act(async () => confirm.click());
  expect(state.revokeUsers).toHaveBeenCalledWith({ revokePlatformAccessUsers: { user_ids: ["a"] } });
});

it("filters by access overlap, restarts at page one and clears the selection", () => {
  twoUsers();
  render("");
  act(() => checkboxes()[1].click());
  act(() => chip("rework.platformAccess.overlapFilter.rule").click());
  expect(lastUsersQuery()).toMatchObject({ overlap: "rule", offset: 0, exceptionsOnly: true });
  expect(checkboxes().some((box) => box.checked)).toBe(false);
  act(() => chip("rework.platformAccess.overlapFilter.unknown").click());
  expect(lastUsersQuery()).toMatchObject({ overlap: "unknown", offset: 0 });
  act(() => chip("rework.platformAccess.overlapFilter.all").click());
  expect(lastUsersQuery()).not.toHaveProperty("overlap");
});

it("switches the table to emails waiting for a first sign-in, and removes one or a selection", async () => {
  state.pending = [
    { email: "jane@example.org", granted_by: "admin", granted_at: "2026-11-13T10:00:00Z" },
    { email: "paul@example.org", granted_by: "admin", granted_at: "2026-11-12T10:00:00Z" },
  ];
  render("");
  expect(usersPanel().textContent).not.toContain("jane@example.org");
  expect(chip("rework.platformAccess.overlapFilter.pending").textContent).toContain("2");
  act(() => chip("rework.platformAccess.overlapFilter.pending").click());
  // People are not requested while the pending emails are shown.
  expect(state.searchUsers.mock.lastCall![1]).toEqual({ skip: true });
  expect(usersPanel().textContent).toContain("jane@example.org");
  const row = [...usersPanel().querySelectorAll<HTMLElement>('[class*="datatable-row"]')].find((node) =>
    node.textContent?.includes("jane@example.org"),
  )!;
  const remove = [...row.querySelectorAll("button")].find(
    (node) => node.textContent === "rework.platformAccess.remove",
  )!;
  await act(async () => remove.click());
  expect(state.removeEmail).toHaveBeenCalledWith({
    removePlatformAccessPendingEmails: { emails: ["jane@example.org"] },
  });
  act(() => checkboxes()[0].click());
  act(() => checkboxes()[1].click());
  act(() => chip("rework.platformAccess.selection.remove").click());
  const confirm = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent === "rework.platformAccess.bulkRemove.confirm",
  )!;
  await act(async () => confirm.click());
  expect(state.removeEmail).toHaveBeenLastCalledWith({
    removePlatformAccessPendingEmails: { emails: ["paul@example.org"] },
  });
  expect(state.revokeUsers).not.toHaveBeenCalled();
});

it("whitelists typed emails alongside selected people", async () => {
  state.pickedEmails = ["jane@example.org"];
  render("");
  act(() => addUsersButton().click());
  await act(async () => pageButton("Confirm selection").click());
  expect(state.bulk).toHaveBeenCalledWith({ grantPlatformAccessUsers: { user_ids: ["first", "second"] } });
  expect(state.addEmail).toHaveBeenCalledWith({ addPlatformAccessPendingEmail: { email: "jane@example.org" } });
});

it("shows when and how each individual access was added, and one chip detailing the other access", () => {
  state.users = [
    {
      user_id: "manual",
      username: "Alice",
      email: null,
      sources: [
        { kind: "attribute" },
        { kind: "manual", granted_at: "2026-03-04T10:20:30Z" },
        { kind: "team", team_id: "demo", team_name: "Demo" },
        { kind: "free", team_id: "open", team_name: "Open" },
        { kind: "team", team_id: "labs", team_name: "Labs" },
        { kind: "admin" },
      ],
    },
    {
      user_id: "linked",
      username: "Chloe",
      email: null,
      sources: [
        { kind: "manual", granted_at: "2026-02-02T09:00:00Z" },
        { kind: "free", team_id: "open-uid", team_name: null },
      ],
    },
    {
      user_id: "imported",
      username: "Bob",
      email: null,
      sources: [{ kind: "t0", granted_at: "2025-12-31T08:00:00Z" }],
    },
  ];
  render("");
  const panel = host.querySelector<HTMLElement>('[id$="-users-panel"]')!;
  const headers = [...panel.querySelectorAll(`[class*="datatable-header"] > [class*="datatable-cell"]`)].map(
    (node) => node.textContent,
  );
  expect(headers).toEqual([
    // The selection column's header holds only the select-all checkbox.
    "",
    "rework.teamSettings.members.table.identifiant",
    "rework.teamSettings.members.table.firstName",
    "rework.teamSettings.members.table.lastName",
    "rework.platformAccess.addedOn",
    "rework.platformAccess.origin.label",
    "rework.platformAccess.otherAccess.label",
    "rework.platformAccess.exception",
  ]);
  const row = (name: string) =>
    [...panel.querySelectorAll<HTMLElement>(`[class*="datatable-row"]`)].find((node) =>
      node.textContent?.includes(name),
    )!;
  const cells = (name: string) => [...row(name).querySelectorAll<HTMLElement>(`:scope > [class*="datatable-cell"]`)];
  // The selection checkbox comes first.
  const [, , , , aliceDate, aliceOrigin, aliceOthers] = cells("Alice");
  expect(aliceDate.textContent).toBe(new Date("2026-03-04T10:20:30Z").toLocaleString("en"));
  expect(aliceOrigin.textContent).toBe("rework.platformAccess.origin.manual");
  // One chip whatever the number of other sources, focusable, named with the whole list.
  expect(aliceOthers.textContent).toBe("rework.platformAccess.otherAccess.label");
  const trigger = aliceOthers.querySelector<HTMLElement>('[role="note"]')!;
  expect(trigger.tabIndex).toBe(0);
  const grouped = [
    "rework.platformAccess.otherAccess.attribute",
    "rework.platformAccess.otherAccess.admin",
    "rework.platformAccess.otherAccess.team[Demo, Labs]",
    "rework.platformAccess.otherAccess.free[Open]",
  ];
  // The mocked translation returns keys, so the localized separator and sentence show up as their keys.
  expect(state.translated).toHaveBeenCalledWith("rework.platformAccess.otherAccess.summary", {
    details: grouped.join("rework.platformAccess.otherAccess.separator"),
  });
  expect(trigger.getAttribute("aria-label")).toBe("rework.platformAccess.otherAccess.summary");
  expect(document.querySelector('[role="tooltip"]')).toBeNull();
  act(() => {
    trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  });
  const tooltip = document.querySelector<HTMLElement>('[role="tooltip"]')!;
  expect([...tooltip.querySelectorAll(":scope > span > span")].map((line) => line.textContent)).toEqual(grouped);
  expect(trigger.getAttribute("aria-describedby")).toBe(tooltip.id);
  act(() => {
    trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
  });

  // Only the groups that apply are listed, and a team without a name never shows its identifier.
  const chloe = cells("Chloe")[6].querySelector<HTMLElement>('[role="note"]')!;
  expect(chloe.getAttribute("aria-label")).toBe("rework.platformAccess.otherAccess.summary");
  expect(state.translated).toHaveBeenCalledWith("rework.platformAccess.otherAccess.summary", {
    details: "rework.platformAccess.otherAccess.free[rework.platformAccess.otherAccess.unnamedTeam]",
  });
  expect(state.translated).not.toHaveBeenCalledWith(
    "rework.platformAccess.otherAccess.summary",
    expect.objectContaining({ details: expect.stringContaining("open-uid") }),
  );

  const [, , , , bobDate, bobOrigin, bobOthers] = cells("Bob");
  expect(bobDate.textContent).toBe(new Date("2025-12-31T08:00:00Z").toLocaleString("en"));
  expect(bobOrigin.textContent).toBe("rework.platformAccess.origin.t0");
  // Nothing else grants access: the cell is empty, without chip or marker.
  expect(bobOthers.textContent).toBe("");
  expect(bobOthers.querySelector('[role="note"]')).toBeNull();
  expect(panel.querySelectorAll('[role="note"]')).toHaveLength(2);
});

it("confirms a removal and stays silent on failure", async () => {
  render("");
  await act(async () => pageButton("rework.platformAccess.remove").click());
  expect(state.revoke).toHaveBeenCalledWith({ userId: "user" });
  expect(state.success).toHaveBeenLastCalledWith({ summary: "rework.platformAccess.revokedUser" });
  expect(state.success).toHaveBeenCalledTimes(1);
  state.revoke.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("Unsuccessful removal");
    },
  }));
  await act(async () => pageButton("rework.platformAccess.remove").click());
  expect(state.success).toHaveBeenCalledTimes(1);
});

it("steps back a single page when a removal empties the last page", () => {
  const next = () =>
    act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  state.usersTotal = 41;
  render("");
  next();
  next();
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 40 });
  // The only row of page 3 is removed: the list lands on page 2, not back on page 1.
  state.users = [];
  state.usersTotal = 40;
  act(() => root.render(<PlatformAccessPage />));
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 20 });
  // Same from page 2 of 2: page 1.
  state.usersTotal = 20;
  act(() => root.render(<PlatformAccessPage />));
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 0 });
});

it("changes the users page size from the first page, asking for the new limit", () => {
  state.usersTotal = 120;
  render("");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 20, limit: 20 });
  const panel = host.querySelector<HTMLElement>('[id$="-users-panel"]')!;
  const pageSize = panel.querySelector<HTMLButtonElement>('[aria-label="dataTable.pagination.itemsPerPage"]')!;
  act(() => pageSize.click());
  const options = [...document.querySelectorAll<HTMLElement>('[role="option"]')];
  expect(options.map((option) => option.textContent)).toEqual(["20", "50", "100"]);
  act(() => options[1].click());
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 0, limit: 50, query: "", exceptionsOnly: true });
  expect(pageSize.textContent).toContain("50");
  // The chosen size survives a visit to another tab.
  openTab("teams");
  openTab("users");
  expect(state.searchUsers.mock.lastCall).toEqual([
    { offset: 0, limit: 50, query: "", exceptionsOnly: true },
    { skip: false },
  ]);
});

const dialog = () => host.querySelector<HTMLElement>('[data-testid="add-users-dialog"]');

it("opens the add dialog, grants its selection in one call, confirms and closes", async () => {
  render("");
  expect(dialog()).toBeNull();
  act(() => addUsersButton().click());
  expect(dialog()).not.toBeNull();
  await act(async () => pageButton("Confirm selection").click());
  expect(state.bulk).toHaveBeenCalledTimes(1);
  expect(state.bulk).toHaveBeenCalledWith({ grantPlatformAccessUsers: { user_ids: ["first", "second"] } });
  expect(state.success).toHaveBeenCalledWith({ summary: "rework.platformAccess.grantedSelected" });
  expect(dialog()).toBeNull();
});

it("returns to the first page of the unfiltered list after an add, where the newest are listed", async () => {
  state.usersTotal = 60;
  render("Al");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 20, query: "Al" });
  act(() => addUsersButton().click());
  await act(async () => pageButton("Confirm selection").click());
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 0, limit: 20, query: "", exceptionsOnly: true });
  expect(host.querySelector<HTMLInputElement>('[id$="-users-panel"] input[type="text"]')!.value).toBe("");
  // No delayed search brings the old text back.
  act(() => vi.advanceTimersByTime(300));
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 0, query: "" });
});

it("keeps the page and the search after a failed add", async () => {
  state.usersTotal = 60;
  state.bulk.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("Unsuccessful grant");
    },
  }));
  render("Al");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  act(() => addUsersButton().click());
  await act(async () => pageButton("Confirm selection").click());
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 20, query: "Al" });
});

it("keeps the add dialog open and stays silent after a failed grant", async () => {
  state.bulk.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("Unsuccessful grant");
    },
  }));
  render("");
  act(() => addUsersButton().click());
  await act(async () => pageButton("Confirm selection").click());
  expect(dialog()).not.toBeNull();
  expect(state.success).not.toHaveBeenCalled();
  act(() => pageButton("Close dialog").click());
  expect(dialog()).toBeNull();
});

it("marks the add dialog busy while the grant is being saved", async () => {
  let finish!: () => void;
  state.bulk.mockImplementationOnce(() => ({
    unwrap: () =>
      new Promise<undefined>((resolve) => {
        finish = () => resolve(undefined);
      }),
  }));
  render("");
  act(() => addUsersButton().click());
  await act(async () => pageButton("Confirm selection").click());
  expect(dialog()?.dataset.busy).toBe("true");
  await act(async () => finish());
  expect(dialog()).toBeNull();
});

it("grants more than 100 selections without a product cap", async () => {
  state.picked = Array.from({ length: 101 }, (_, index) => `user-${index}`);
  render("");
  act(() => addUsersButton().click());
  await act(async () => pageButton("Confirm selection").click());
  expect(state.bulk.mock.calls[0][0].grantPlatformAccessUsers.user_ids).toHaveLength(101);
});

it("keeps the pagination but no stale rows while another page or search loads", () => {
  state.usersTotal = 60;
  render("");
  expect(host.textContent).toContain("Alice");
  state.usersFetching = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(host.textContent).not.toContain("Alice");
  expect(host.querySelector('button[aria-label="dataTable.pagination.next"]')).not.toBeNull();
});

it("hides earlier rows during a search request or a failed search", () => {
  render();
  state.usersFetching = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(host.textContent).not.toContain("Alice");
  state.usersFetching = false;
  state.usersError = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(host.textContent).not.toContain("Alice");
});

it("states next to the title whether filtering is on", () => {
  act(() => root.render(<PlatformAccessPage />));
  const title = () => host.querySelector("h1")!.parentElement!.textContent;
  expect(title()).toContain("rework.platformAccess.filteringOff");
  state.filteringEnabled = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(title()).toContain("rework.platformAccess.filteringOn");
});

it("titles each whitelist tab and describes it above its controls", () => {
  render();
  expect(host.querySelectorAll("h3")).toHaveLength(0);
  for (const [tab, title, hint] of [
    ["users", "rework.platformAccess.whitelistedUsers", "rework.platformAccess.whitelistedUsersHint"],
    ["teams", "rework.platformAccess.whitelistedTeams", "rework.platformAccess.whitelistedTeamsHint"],
  ]) {
    const panel = host.querySelector<HTMLElement>(`[id$="-${tab}-panel"]`)!;
    expect([...panel.querySelectorAll("h2")].map((node) => node.textContent)).toEqual([title]);
    // Title then description head the block, before any control.
    const header = panel.firstElementChild!;
    expect([...header.children].map((node) => [node.tagName, node.textContent])).toEqual([
      ["H2", title],
      ["P", hint],
    ]);
    expect(header.querySelector("input, button")).toBeNull();
  }
});

it("offers one level of three tabs, exposes only the selected panel and follows the keyboard", () => {
  act(() => root.render(<PlatformAccessPage />));
  expect(host.querySelectorAll('[role="tablist"]')).toHaveLength(1);
  const tabs = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  expect(tabs.map((tab) => tab.textContent)).toEqual([
    "rework.platformAccess.tabs.rules",
    "rework.platformAccess.tabs.users",
    "rework.platformAccess.tabs.teams",
  ]);
  const panels = [...host.querySelectorAll<HTMLDivElement>('[role="tabpanel"]')];
  expect(panels).toHaveLength(3);
  panels.forEach((panel, index) => {
    expect(panel.getAttribute("aria-labelledby")).toBe(tabs[index].id);
    expect(tabs[index].getAttribute("aria-controls")).toBe(panel.id);
  });
  expect(visiblePanels()).toEqual([panels[0]]);
  const enable = () =>
    [...host.querySelectorAll("button")].find((node) => node.textContent === "rework.platformAccess.activation.enable");
  for (const index of [1, 2]) {
    act(() => tabs[index - 1].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(document.activeElement).toBe(tabs[index]);
    expect(tabs[index].getAttribute("aria-selected")).toBe("true");
    expect(visiblePanels()).toEqual([panels[index]]);
    // The filtering action of the page header stays available on every tab.
    expect(enable()).toBeDefined();
  }
});

it("keeps user controls in Users and team authorization in Teams", () => {
  render();
  const userPanel = host.querySelector<HTMLElement>('[id$="-users-panel"]')!;
  const teamPanel = host.querySelector<HTMLElement>('[id$="-teams-panel"]')!;
  expect(userPanel.textContent).toContain("rework.platformAccess.remove");
  expect(userPanel.textContent).toContain("rework.platformAccess.addUsers");
  expect(userPanel.querySelector('[aria-label="rework.platformAccess.moreActions"]')).not.toBeNull();
  expect(userPanel.hidden).toBe(false);
  expect(teamPanel.hidden).toBe(true);
  openTab("teams");
  expect(userPanel.hidden).toBe(true);
  expect(teamPanel.hidden).toBe(false);
  expect(teamPanel.querySelector('input[aria-label="rework.platformAccess.allowTeam Demo"]')).not.toBeNull();
  expect(teamPanel.textContent).not.toContain("rework.platformAccess.links.manage");
  expect(teamPanel.textContent).not.toContain("rework.platformAccess.freeHint");
});

it("narrows the teams table ignoring accents and case, says when nothing matches, and clears", () => {
  state.teams = [
    { team_id: "t1", name: "Équipe Démos", allowed: false, free: false },
    { team_id: "t2", name: "Innovation", allowed: true, free: false },
    { team_id: "t3", name: "Qualite", allowed: false, free: false },
    { team_id: "sans-nom", name: null, allowed: false, free: false },
  ];
  act(() => root.render(<PlatformAccessPage />));
  openTab("teams");
  const panel = host.querySelector<HTMLElement>('[id$="-teams-panel"]')!;
  const input = panel.querySelector<HTMLInputElement>('input[type="text"]')!;
  const searchTeams = (value: string) =>
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  const listed = () =>
    [...panel.querySelectorAll(`[class*="datatable-row"]`)].map(
      (row) => row.querySelector(`[class*="datatable-cell"]`)!.textContent,
    );
  expect(listed()).toEqual(["Équipe Démos", "Innovation", "Qualite", "sans-nom"]);
  // Accent missing from the query, present in the query only, and a different case.
  searchTeams("equipe demos");
  expect(listed()).toEqual(["Équipe Démos"]);
  searchTeams("  QUALITÉ ");
  expect(listed()).toEqual(["Qualite"]);
  searchTeams("ÎNNOV");
  expect(listed()).toEqual(["Innovation"]);
  searchTeams("SANS");
  expect(listed()).toEqual(["sans-nom"]);
  expect(panel.textContent).not.toContain("rework.platformAccess.noTeams");
  searchTeams("zzz");
  expect(listed()).toEqual([]);
  expect(panel.textContent).toContain("rework.platformAccess.noTeams");
  // No empty table is left under the line: neither its header nor its pagination.
  expect(panel.querySelector('[class*="datatable"]')).toBeNull();
  expect(panel.textContent).not.toContain("rework.platformAccess.teamAllowed");
  act(() => panel.querySelector<HTMLButtonElement>('button[aria-label="rework.platformAccess.clearSearch"]')!.click());
  expect(input.value).toBe("");
  expect(listed()).toHaveLength(4);
  expect(panel.textContent).not.toContain("rework.platformAccess.noTeams");
  expect(state.setTeam).not.toHaveBeenCalled();
});

it("shows only allowed teams on demand and sorts teams by name from the header", () => {
  state.teams = [
    { team_id: "t1", name: "Zeta", allowed: true, free: false },
    { team_id: "t2", name: "Alpha", allowed: false, free: false },
    { team_id: "t3", name: "Mu", allowed: true, free: false },
  ];
  act(() => root.render(<PlatformAccessPage />));
  openTab("teams");
  const panel = host.querySelector<HTMLElement>('[id$="-teams-panel"]')!;
  const listed = () =>
    [...panel.querySelectorAll(`[class*="datatable-row"]`)].map(
      (row) => row.querySelector(`[class*="datatable-cell"]`)!.textContent,
    );
  const chip = (label: string) =>
    [...panel.querySelectorAll<HTMLButtonElement>('[role="group"] button')].find((button) =>
      button.textContent!.startsWith(label),
    )!;
  expect(chip("rework.platformAccess.teamFilter.allowed").textContent).toContain("2");
  act(() => chip("rework.platformAccess.teamFilter.allowed").click());
  expect(listed()).toEqual(["Zeta", "Mu"]);
  const nameHeader = [...panel.querySelectorAll<HTMLButtonElement>('[class*="header-sort-button"]')].find((button) =>
    button.textContent!.startsWith("rework.platformAccess.team"),
  )!;
  act(() => nameHeader.click());
  expect(listed()).toEqual(["Mu", "Zeta"]);
  act(() => nameHeader.click());
  expect(listed()).toEqual(["Zeta", "Mu"]);
  act(() => chip("rework.platformAccess.teamFilter.all").click());
  expect(listed()).toEqual(["Zeta", "Mu", "Alpha"]);
  expect(state.setTeam).not.toHaveBeenCalled();
});

it("whitelists a whole team while retaining its independent Free enrollment flag", async () => {
  render();
  openTab("teams");
  const toggle = host.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.allowTeam Demo"]')!;
  await act(async () => toggle.click());
  expect(state.setTeam).toHaveBeenCalledWith({
    teamId: "demo",
    setPlatformAccessTeam: { allowed: true, free: true },
  });
  expect(state.bulk).not.toHaveBeenCalled();
});

it("preserves the rule draft, the search and the page across tabs without mutations", async () => {
  state.usersTotal = 60;
  act(() => root.render(<PlatformAccessPage />));
  act(() => [...host.querySelectorAll("button")].find((node) => node.textContent === "Edit draft")!.click());
  openTab("users");
  search("Al");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  openTab("rules");
  expect(host.querySelector('[role="tabpanel"]:not([hidden])')?.textContent).toContain("Unsaved rule");
  openTab("users");
  openTab("teams");
  openTab("users");
  expect(state.searchUsers.mock.lastCall).toEqual([
    { offset: 20, limit: 20, query: "Al", exceptionsOnly: true },
    { skip: false },
  ]);
  expect(state.bulk).not.toHaveBeenCalled();
  expect(state.revoke).not.toHaveBeenCalled();
  expect(state.importT0).not.toHaveBeenCalled();
});
const moreMenu = () => host.querySelector<HTMLButtonElement>('[aria-label="rework.platformAccess.moreActions"]')!;
const menuOptions = () => [...document.querySelectorAll<HTMLElement>('[role="option"]')];
it("keeps the import in the more menu, next to the add button, and runs it from there", async () => {
  render();
  expect(addUsersButton().textContent).toContain("rework.platformAccess.addUsers");
  expect(addUsersButton().nextElementSibling?.contains(moreMenu())).toBe(true);
  act(() => moreMenu().click());
  const option = menuOptions().find((node) => node.textContent?.includes("rework.platformAccess.t0Import"))!;
  act(() => option.click());
  // Never on the click alone: a dialog states how many accounts it adds first.
  expect(state.importT0).not.toHaveBeenCalled();
  expect(document.body.textContent).toContain("rework.platformAccess.t0Confirm.message");
  const confirm = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent === "rework.platformAccess.t0Confirm.confirm",
  )!;
  await act(async () => confirm.click());
  expect(state.importT0).toHaveBeenCalledTimes(1);
});

it("says so when a search matches no user and shows progress while searching", () => {
  state.users = [];
  render();
  const panel = host.querySelector<HTMLElement>('[id$="-users-panel"]')!;
  expect(panel.textContent).toContain("rework.platformAccess.noUsers");
  expect(panel.querySelector('input[type="checkbox"]')).toBeNull();
  state.usersFetching = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(panel.textContent).not.toContain("rework.platformAccess.noUsers");
  expect(panel.querySelector('[role="status"]')).not.toBeNull();
  state.usersFetching = false;
  search("");
  expect(panel.textContent).not.toContain("rework.platformAccess.noUsers");
});

it("requires configuration and confirmation across all tabs before activating", async () => {
  state.configured = false;
  render();
  const action = () =>
    [...host.querySelectorAll<HTMLButtonElement>("button")].find(
      (node) => node.textContent === "rework.platformAccess.activation.enable",
    )!;
  expect(host.querySelector("h1")?.parentElement?.parentElement?.parentElement?.contains(action())).toBe(true);
  expect(action().disabled).toBe(true);
  state.configured = true;
  render();
  for (const tab of ["rules", "users"]) {
    openTab(tab);
    expect(action().disabled).toBe(false);
  }
  openTab("teams");
  expect(action().disabled).toBe(false);
  act(() => action().click());
  expect(state.filter).not.toHaveBeenCalled();
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("rework.platformAccess.activation.groups");
  expect(dialog.querySelector(`.${styles.importWarning}`)?.getAttribute("role")).toBe("alert");
  expect(dialog.textContent).toContain("rework.platformAccess.activation.importWarning");
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.activation.goToWhitelist")!
      .click(),
  );
  expect(state.filter).not.toHaveBeenCalled();
  expect(visiblePanels().some((p) => p.id.endsWith("-users-panel"))).toBe(true);
  expect(visiblePanels().some((p) => p.id.endsWith("-teams-panel"))).toBe(false);
  act(() => action().click());
  await act(async () =>
    [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')]
      .find((node) => node.textContent === "rework.platformAccess.activation.continueWithoutImport")!
      .click(),
  );
  expect(state.filter).toHaveBeenCalledWith({
    setPlatformFiltering: { filtering_enabled: true, expected_revision: 1 },
  });
});

const filteringAction = () =>
  [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent === `rework.platformAccess.activation.${state.filteringEnabled ? "disable" : "enable"}`,
  )!;
const dialogButton = (key: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(
    (node) => node.textContent === key || node.getAttribute("aria-label") === key,
  )!;

it("uses normal activation confirmation after a completed import", async () => {
  state.completed = true;
  render();
  act(() => filteringAction().click());
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain(
    "rework.platformAccess.activation.importWarning",
  );
  await act(async () => dialogButton("rework.platformAccess.activation.enable").click());
  expect(state.filter).toHaveBeenCalledWith({
    setPlatformFiltering: { filtering_enabled: true, expected_revision: 1 },
  });
  expect(state.importT0).not.toHaveBeenCalled();
});

it("prevents unknown import status from bypassing consent and offers retry", async () => {
  state.completed = true;
  state.importError = true;
  render();
  act(() => filteringAction().click());
  expect(dialogButton("rework.platformAccess.activation.enable").disabled).toBe(true);
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    "rework.platformAccess.activation.importStatusFailed",
  );
  act(() => dialogButton("rework.platformAccess.retry").click());
  expect(state.retryImport).toHaveBeenCalledOnce();
  state.importError = false;
  state.importFetching = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.enable").disabled).toBe(true);
  state.importFetching = false;
  state.importMissing = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.enable").disabled).toBe(true);
  state.importMissing = false;
  state.completed = false;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(false);
  expect(state.filter).not.toHaveBeenCalled();
});

it("retains preview safeguards when continuing without importing", () => {
  render();
  act(() => filteringAction().click());
  for (const condition of ["previewFetching", "previewError"] as const) {
    state[condition] = true;
    act(() => root.render(<PlatformAccessPage />));
    expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(true);
    state[condition] = false;
  }
  state.previewRevision = 2;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(true);
  state.previewRevision = 1;
  state.authorityRevision = 1;
  state.authorityError = false;
  state.authorityFetching = false;
  state.configured = false;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(true);
  expect(state.filter).not.toHaveBeenCalled();
});

it("does not require import status to disable filtering", async () => {
  state.filteringEnabled = true;
  state.importError = true;
  state.importMissing = true;
  render();
  act(() => filteringAction().click());
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain(
    "rework.platformAccess.activation.importWarning",
  );
  expect(dialogButton("rework.platformAccess.activation.disable").disabled).toBe(false);
  await act(async () => dialogButton("rework.platformAccess.activation.disable").click());
  expect(state.filter).toHaveBeenCalledWith({
    setPlatformFiltering: { filtering_enabled: false, expected_revision: 1 },
  });
});

it("prevents double activation and dismissal during the activation mutation", async () => {
  let finish!: () => void;
  state.filter.mockImplementationOnce(() => ({
    unwrap: () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  }));
  render();
  act(() => filteringAction().click());
  await act(async () => dialogButton("rework.platformAccess.activation.continueWithoutImport").click());
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(true);
  act(() => dialogButton("rework.platformAccess.activation.goToWhitelist").click());
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  expect(state.filter).toHaveBeenCalledOnce();
  await act(async () => finish());
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("refreshes the read-only review and hides stale users while loading", () => {
  state.previewUsers = [{ user_id: "original", username: "Before", email: null, outcome: "allowed", sources: [] }];
  render();
  act(() => filteringAction().click());
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("Before");
  act(() => dialogButton("rework.platformAccess.activation.update").click());
  expect(state.refreshPreview).toHaveBeenCalledOnce();
  expect(state.refreshAuthority).toHaveBeenCalledOnce();
  expect(state.retryImport).toHaveBeenCalledOnce();
  expect(state.filter).not.toHaveBeenCalled();
  expect(state.importT0).not.toHaveBeenCalled();
  state.previewFetching = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.update").disabled).toBe(true);
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(true);
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain("Before");
  state.previewFetching = false;
  state.previewUsers = [{ user_id: "latest", username: "Latest", email: null, outcome: "allowed", sources: [] }];
  act(() => root.render(<PlatformAccessPage />));
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("Latest");
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain("Before");
});

it("keeps unevaluable accounts outside the two main result lists", () => {
  state.previewUsers = [
    { user_id: "known", username: "Known", email: null, outcome: "allowed", sources: [] },
    { user_id: "unverified", username: "Unverified", email: null, outcome: "unknown", sources: [] },
  ];
  render();
  act(() => filteringAction().click());
  expect(document.querySelector('[role="dialog"]')?.querySelectorAll('[role="tab"]')).toHaveLength(2);
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("Known");
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain("Uncertain");
  const dialog = document.querySelector('[role="dialog"]')!;
  const disclosure = [...dialog.querySelectorAll<HTMLButtonElement>("button[aria-expanded]")].find((node) =>
    node.textContent?.includes("rework.platformAccess.activation.unverified"),
  )!;
  expect(disclosure.getAttribute("aria-expanded")).toBe("false");
  expect(dialog.textContent).not.toContain("Unverified");
  act(() => disclosure.click());
  expect(disclosure.getAttribute("aria-expanded")).toBe("true");
  expect(dialog.textContent).toContain("Unverified");
  expect(dialog.textContent).toContain("rework.platformAccess.activation.unknownHint");
  expect(state.filter).not.toHaveBeenCalled();
  expect(
    document.querySelector('[role="dialog"]')?.querySelectorAll('[role="tab"]')[1].getAttribute("aria-selected"),
  ).toBe("true");
});

it("starts with blocked users when present and omits unavailable verification when all are evaluated", () => {
  state.previewUsers = [
    { user_id: "admitted", username: "Admitted", email: null, outcome: "allowed", sources: [] },
    { user_id: "refused", username: "Refused", email: null, outcome: "blocked", sources: [] },
  ];
  render();
  act(() => filteringAction().click());
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("Refused");
  expect(dialog.textContent).not.toContain("Admitted");
  expect(dialog.textContent).not.toContain("rework.platformAccess.activation.unverified");
  expect(dialog.querySelectorAll('[role="tab"]')[0].getAttribute("aria-selected")).toBe("true");
  act(() => (dialog.querySelectorAll('[role="tab"]')[1] as HTMLButtonElement).click());
  expect(dialog.textContent).toContain("Admitted");
  expect(dialog.textContent).not.toContain("Refused");
});

it("recovers a changed authority revision on Update before confirming the refreshed review", async () => {
  render();
  act(() => filteringAction().click());
  state.previewRevision = 2;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(true);
  act(() => dialogButton("rework.platformAccess.activation.update").click());
  expect(state.refreshAuthority).toHaveBeenCalledOnce();
  expect(state.refreshPreview).toHaveBeenCalledOnce();
  expect(state.filter).not.toHaveBeenCalled();
  state.authorityRevision = 2;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.continueWithoutImport").disabled).toBe(false);
  await act(async () => dialogButton("rework.platformAccess.activation.continueWithoutImport").click());
  expect(state.filter).toHaveBeenCalledWith({
    setPlatformFiltering: { filtering_enabled: true, expected_revision: 2 },
  });
});

it("keeps authority read failures recoverable without allowing confirmation", () => {
  state.completed = true;
  render();
  act(() => filteringAction().click());
  act(() => dialogButton("rework.platformAccess.activation.update").click());
  state.authorityError = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(dialogButton("rework.platformAccess.activation.enable").disabled).toBe(true);
  expect(dialogButton("rework.platformAccess.activation.update").disabled).toBe(false);
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    "rework.platformAccess.activation.previewFailed",
  );
  act(() => dialogButton("rework.platformAccess.retry").click());
  expect(state.refreshAuthority).toHaveBeenCalledTimes(2);
  expect(state.filter).not.toHaveBeenCalled();
  act(() =>
    document
      .querySelector('[role="dialog"]')!
      .dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })),
  );
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("shows a supported page size and lets the administrator change it", () => {
  state.previewUsers = Array.from({ length: 21 }, (_, index) => ({
    user_id: `preview-${index}`,
    username: `Preview person ${index}`,
    email: null,
    outcome: "allowed",
    sources: [],
  }));
  render();
  act(() => filteringAction().click());
  const dialog = document.querySelector('[role="dialog"]')!;
  const pageSize = dialog.querySelector<HTMLButtonElement>('[aria-label="dataTable.pagination.itemsPerPage"]')!;
  expect(pageSize.textContent).toContain("20");
  expect(dialog.textContent).not.toContain("Preview person 20");
  act(() => pageSize.click());
  const fifty = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(
    (option) => option.textContent === "50",
  )!;
  act(() => fifty.click());
  expect(pageSize.textContent).toContain("50");
  expect(dialog.textContent).toContain("Preview person 20");
  expect(state.filter).not.toHaveBeenCalled();
});

it("offers the reimport from the more menu after completion, with filtering on or off", () => {
  state.completed = true;
  act(() => root.render(<PlatformAccessPage />));
  openTab("users");
  expect(moreMenu().disabled).toBe(false);
  act(() => moreMenu().click());
  const labels = menuOptions().map((node) => node.textContent);
  expect(labels).toEqual(["rework.platformAccess.t0Import"]);
  expect(state.importT0).not.toHaveBeenCalled();
  state.filteringEnabled = true;
  act(() => root.render(<PlatformAccessPage />));
  expect(moreMenu().disabled).toBe(false);
});

it("explains an empty filter with its own empty state, and offers adding only on an empty whitelist", () => {
  state.users = [];
  render("");
  expect(usersPanel().textContent).toContain("rework.platformAccess.emptyState.emptyHint");
  const addButtons = () =>
    [...usersPanel().querySelectorAll("button")].filter((node) =>
      node.textContent?.includes("rework.platformAccess.addUsers"),
    );
  // The toolbar's button and the empty state's.
  expect(addButtons()).toHaveLength(2);
  act(() => chip("rework.platformAccess.overlapFilter.unknown").click());
  expect(addButtons()).toHaveLength(1);
  expect(usersPanel().textContent).toContain("rework.platformAccess.emptyState.unknown.title");
  expect(usersPanel().textContent).toContain("rework.platformAccess.emptyState.unknown.hint");
  expect(usersPanel().textContent).not.toContain("rework.platformAccess.emptyState.emptyHint");
});

it("shows how many people each cleanup chip lists, counted once per search", () => {
  render("");
  expect(chip("rework.platformAccess.overlapFilter.rule").textContent).toContain("4");
  expect(chip("rework.platformAccess.overlapFilter.whitelistOnly").textContent).toContain("7");
  expect(chip("rework.platformAccess.overlapFilter.unknown").textContent).toContain("2");
  const calls = state.countQueries.mock.calls.length;
  act(() => pageButton("2")?.click());
  search("bo");
  expect(state.countQueries.mock.lastCall).toEqual([{ query: "bo" }, { skip: false }]);
  expect(state.countQueries.mock.calls.length).toBeGreaterThan(calls);
});
