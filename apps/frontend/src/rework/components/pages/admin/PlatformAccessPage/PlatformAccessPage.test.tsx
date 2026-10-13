// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, useState } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import type { PlatformAccessActivationUser } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const state = vi.hoisted(() => ({
  users: [
    {
      user_id: "user",
      username: "Alice",
      email: "alice@example.org",
      sources: [{ kind: "free", team_id: "demo", team_name: "Demo" }],
    },
  ],
  searchUsers: vi.fn(),
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
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
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
    if ((options as { skip: boolean }).skip) return { isFetching: false, isError: false };
    return {
      isFetching: state.usersFetching,
      isError: state.usersError,
      data: { total: 1, items: [{ user_id: "old", username: "Previous search", sources: [] }] },
      currentData: state.usersFetching
        ? undefined
        : { total: state.usersTotal ?? state.users.length, items: state.users },
    };
  },
  usePlatformAccessT0Query: () => ({
    isFetching: state.importFetching,
    isError: state.importError,
    refetch: state.retryImport,
    data: state.importMissing
      ? undefined
      : { candidates: 1, matching: 0, completed_at: state.completed ? "2026-01-01" : null },
  }),
  usePlatformAccessTeamsQuery: () => ({
    data: [{ team_id: "demo", name: "Demo", allowed: false, free: true, has_enrollment_link: true }],
  }),
  useSetPlatformFilteringMutation: () => [state.filter],
  useGrantPlatformUsersMutation: () => [state.bulk],
  useRevokePlatformUserMutation: () => [state.revoke],
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
    onConfirm: (ids: string[]) => void;
  }) =>
    open ? (
      <div data-testid="add-users-dialog" data-busy={busy}>
        <button type="button" onClick={() => onConfirm(state.picked)}>
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
const openWhitelistTab = (tab: string) =>
  act(() =>
    [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
      .find((node) => node.textContent === `rework.platformAccess.whitelistTabs.${tab}`)!
      .click(),
  );
const visiblePanels = () =>
  [...host.querySelectorAll<HTMLElement>('[role="tabpanel"]')].filter((p) => !p.closest("[hidden]"));
const search = (value: string) => {
  const input = host.querySelector<HTMLInputElement>('[id$="-whitelist-users-panel"] input[type="text"]')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  act(() => vi.advanceTimersByTime(300));
};
const type = (value: string) => {
  const input = host.querySelector<HTMLInputElement>('[id$="-whitelist-users-panel"] input[type="text"]')!;
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
    { offset: 0, limit: 25, query: "", exceptionsOnly: true },
    { skip: false },
  ]);
  expect(host.textContent).toContain("Alice");
  expect(host.textContent).not.toContain("Previous search");
  openWhitelistTab("teams");
  expect(state.searchUsers.mock.lastCall?.[1]).toEqual({ skip: true });
  openWhitelistTab("users");
  expect(state.searchUsers.mock.lastCall?.[1]).toEqual({ skip: false });
  openTab("rules");
  expect(state.searchUsers.mock.lastCall?.[1]).toEqual({ skip: true });
});

it("waits for a pause in typing, trims the search and restarts at the first page", () => {
  state.usersTotal = 60;
  render("");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 25, limit: 25, query: "", exceptionsOnly: true });
  type(" A");
  type(" Al ");
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 25, limit: 25, query: "", exceptionsOnly: true });
  act(() => vi.advanceTimersByTime(300));
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 0, limit: 25, query: "Al", exceptionsOnly: true });
  expect(state.searchUsers.mock.calls.some(([args]) => args.query === "A")).toBe(false);
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  search("");
  expect(state.searchUsers.mock.lastCall?.[0]).toEqual({ offset: 0, limit: 25, query: "", exceptionsOnly: true });
});

it("tells an empty whitelist apart from a search without match", () => {
  state.users = [];
  render("");
  const panel = host.querySelector<HTMLElement>('[id$="-whitelist-users-panel"]')!;
  expect(panel.textContent).toContain("rework.platformAccess.emptyWhitelist");
  expect(addUsersButton().disabled).toBe(false);
  expect(panel.querySelector('input[type="text"]')).not.toBeNull();
  search("zz");
  expect(panel.textContent).toContain("rework.platformAccess.noUsers");
  expect(panel.textContent).not.toContain("rework.platformAccess.emptyWhitelist");
});

it("offers removal only, without row selection or a bulk bar", () => {
  render("");
  const panel = host.querySelector<HTMLElement>('[id$="-whitelist-users-panel"]')!;
  expect(panel.querySelector('input[type="checkbox"]')).toBeNull();
  expect(pageButton("rework.platformAccess.remove")).toBeDefined();
  expect(host.textContent).toContain("rework.platformAccess.source.free: Demo");
  expect(host.textContent).not.toContain("alice@example.org");
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

it("steps back a page when a removal empties a later page", () => {
  state.usersTotal = 26;
  render("");
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="dataTable.pagination.next"]')!.click());
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 25 });
  state.users = [];
  state.usersTotal = 25;
  act(() => root.render(<PlatformAccessPage />));
  expect(state.searchUsers.mock.lastCall?.[0]).toMatchObject({ offset: 0 });
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

it("names each whitelist panel through its tab only", () => {
  render();
  expect(host.querySelector('[id$="-users-panel"]')?.querySelectorAll("h2, h3")).toHaveLength(0);
  expect(host.querySelector('[id$="-users-panel"]')?.textContent).toContain("rework.platformAccess.whitelistHint");
});

it("exposes only the selected panel and supports keyboard section navigation", () => {
  act(() => root.render(<PlatformAccessPage />));
  const tabs = [
    ...host
      .querySelectorAll<HTMLButtonElement>('[role="tablist"]')[0]
      .querySelectorAll<HTMLButtonElement>('[role="tab"]'),
  ];
  const panels = [...host.querySelectorAll<HTMLDivElement>('[role="tabpanel"]')].filter(
    (p) => !p.id.includes("-whitelist-"),
  );
  expect(tabs).toHaveLength(2);
  expect(visiblePanels()).toEqual([panels[0]]);
  expect(panels[0].getAttribute("aria-labelledby")).toBe(tabs[0].id);
  expect(tabs[0].getAttribute("aria-controls")).toBe(panels[0].id);
  act(() => tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
  expect(document.activeElement).toBe(tabs[1]);
  expect(tabs[1].getAttribute("aria-selected")).toBe("true");
  expect(visiblePanels().map((p) => p.id)).toEqual([
    panels[1].id,
    `${panels[1].id.replace("-users-panel", "")}-whitelist-users-panel`,
  ]);
  expect(
    [...host.querySelectorAll("button")].find((node) => node.textContent === "rework.platformAccess.activation.enable"),
  ).toBeDefined();
});

it("separates user and team whitelist controls with keyboard-accessible sub-tabs", () => {
  render();
  const userPanel = host.querySelector<HTMLElement>('[id$="-whitelist-users-panel"]')!;
  const teamPanel = host.querySelector<HTMLElement>('[id$="-whitelist-teams-panel"]')!;
  expect(userPanel.textContent).toContain("rework.platformAccess.remove");
  expect(userPanel.textContent).toContain("rework.platformAccess.addUsers");
  expect(userPanel.textContent).toContain("rework.platformAccess.t0Import");
  expect(userPanel.hidden).toBe(false);
  expect(teamPanel.hidden).toBe(true);
  const tabs = [
    ...host
      .querySelectorAll<HTMLButtonElement>('[role="tablist"]')[1]
      .querySelectorAll<HTMLButtonElement>('[role="tab"]'),
  ];
  act(() => tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
  expect(document.activeElement).toBe(tabs[1]);
  expect(userPanel.hidden).toBe(true);
  expect(teamPanel.hidden).toBe(false);
  expect(teamPanel.getAttribute("aria-labelledby")).toBe(tabs[1].id);
  expect(tabs[1].getAttribute("aria-controls")).toBe(teamPanel.id);
  expect(teamPanel.querySelector('input[aria-label="rework.platformAccess.allowTeam Demo"]')).not.toBeNull();
  expect(teamPanel.textContent).not.toContain("rework.platformAccess.links.manage");
  expect(teamPanel.textContent).not.toContain("rework.platformAccess.freeHint");
});

it("whitelists a whole team while retaining its independent Free enrollment flag", async () => {
  render();
  openWhitelistTab("teams");
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
  openWhitelistTab("teams");
  openWhitelistTab("users");
  expect(state.searchUsers.mock.lastCall).toEqual([
    { offset: 25, limit: 25, query: "Al", exceptionsOnly: true },
    { skip: false },
  ]);
  expect(state.bulk).not.toHaveBeenCalled();
  expect(state.revoke).not.toHaveBeenCalled();
  expect(state.importT0).not.toHaveBeenCalled();
});
it("reduces the completed import to a discreet status without an import action", () => {
  state.completed = true;
  render();
  expect(host.querySelector('[role="status"]')?.textContent).toContain("rework.platformAccess.t0Done");
  expect(host.textContent).not.toContain("rework.platformAccess.t0Hint");
  expect(
    [...host.querySelectorAll("button")].some((node) => node.textContent === "rework.platformAccess.t0Import"),
  ).toBe(false);
  expect(state.importT0).not.toHaveBeenCalled();
});

it("says so when a search matches no user and shows progress while searching", () => {
  state.users = [];
  render();
  const panel = host.querySelector<HTMLElement>('[id$="-whitelist-users-panel"]')!;
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
  openWhitelistTab("teams");
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
  expect(visiblePanels().some((p) => p.id.endsWith("-whitelist-users-panel"))).toBe(true);
  expect(visiblePanels().some((p) => p.id.endsWith("-whitelist-teams-panel"))).toBe(false);
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
