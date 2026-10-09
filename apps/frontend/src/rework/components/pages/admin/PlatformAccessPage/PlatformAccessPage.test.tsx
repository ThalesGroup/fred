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
  grant: vi.fn(() => ({ unwrap: async () => undefined })),
  importT0: vi.fn(() => ({ unwrap: async () => undefined })),
  setTeam: vi.fn(() => ({ unwrap: async () => undefined })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
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
  usePlatformAccessUsersQuery: () => ({
    data: {
      total: state.users.length,
      items: state.users,
    },
  }),
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
  useGrantPlatformUserMutation: () => [state.grant],
  useRevokePlatformUserMutation: () => [vi.fn()],
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
import PlatformAccessPage from "./PlatformAccessPage";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  state.users = [
    {
      user_id: "user",
      username: "Alice",
      email: "alice@example.org",
      sources: [{ kind: "free", team_id: "demo", team_name: "Demo" }],
    },
  ];
  state.completed = false;
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
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
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
const render = () => {
  act(() => root.render(<PlatformAccessPage />));
  openTab("users");
};

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
  expect(userPanel.querySelector('input[aria-label="rework.platformAccess.selectUser"]')).not.toBeNull();
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
  expect(state.grant).not.toHaveBeenCalled();
});

it("preserves rule drafts and user selections across tabs without mutations", async () => {
  act(() => root.render(<PlatformAccessPage />));
  act(() => [...host.querySelectorAll("button")].find((node) => node.textContent === "Edit draft")!.click());
  openTab("users");
  const selection = host.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.selectUser"]')!;
  await act(async () => selection.click());
  openTab("rules");
  expect(host.querySelector('[role="tabpanel"]:not([hidden])')?.textContent).toContain("Unsaved rule");
  openTab("users");
  expect(selection.checked).toBe(true);
  openWhitelistTab("teams");
  openWhitelistTab("users");
  expect(selection.checked).toBe(true);
  expect(state.bulk).not.toHaveBeenCalled();
  expect(state.grant).not.toHaveBeenCalled();
  expect(state.importT0).not.toHaveBeenCalled();
});
it("shows Free team provenance and offers an independent individual grant", async () => {
  render();
  expect(host.textContent).toContain("rework.platformAccess.source.free: Demo");
  expect(host.textContent).not.toContain("(demo)");
  expect(host.textContent).not.toContain("alice@example.org");
  const button = [...host.querySelectorAll("button")].find(
    (node) => node.textContent === "rework.platformAccess.allow",
  )!;
  await act(async () => button.click());
  expect(state.grant).toHaveBeenCalledWith({ userId: "user" });
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

it("grants selected users and clears selection only on success", async () => {
  render();
  const selection = host.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.selectUser"]')!;
  await act(async () => selection.click());
  const button = [...host.querySelectorAll("button")].find(
    (node) => node.textContent === "rework.platformAccess.allowSelected",
  )!;
  expect(button.disabled).toBe(false);
  await act(async () => button.click());
  expect(state.bulk).toHaveBeenCalledWith({ grantPlatformAccessUsers: { user_ids: ["user"] } });
  expect(selection.checked).toBe(false);
});

it("retains selection across changed search/page results", async () => {
  render();
  await act(async () =>
    host
      .querySelector<HTMLInputElement>('input[type="checkbox"][aria-label="rework.platformAccess.selectUser"]')!
      .click(),
  );
  state.users = [{ user_id: "second", username: "Bob", email: "bob@example.org", sources: [] }];
  render();
  await act(async () =>
    host
      .querySelector<HTMLInputElement>('input[type="checkbox"][aria-label="rework.platformAccess.selectUser"]')!
      .click(),
  );
  await act(async () =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.allowSelected")!
      .click(),
  );
  expect(state.bulk).toHaveBeenCalledWith({ grantPlatformAccessUsers: { user_ids: ["user", "second"] } });
});

it("retains the selected users after a failed grant", async () => {
  state.bulk.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("Unsuccessful grant");
    },
  }));
  render();
  const selection = host.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.selectUser"]')!;
  await act(async () => selection.click());
  await act(async () =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.allowSelected")!
      .click(),
  );
  expect(selection.checked).toBe(true);
});

it("grants more than 100 selections without a product cap", async () => {
  state.users = Array.from({ length: 101 }, (_, index) => ({
    user_id: `user-${index}`,
    username: `User ${index}`,
    email: "",
    sources: [],
  }));
  render();
  const choices = [...host.querySelectorAll<HTMLInputElement>('input[aria-label="rework.platformAccess.selectUser"]')];
  for (const choice of choices) await act(async () => choice.click());
  expect(choices.filter((choice) => choice.checked)).toHaveLength(101);
  expect(choices[100].disabled).toBe(false);
  await act(async () =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.allowSelected")!
      .click(),
  );
  expect(state.bulk.mock.calls[0][0].grantPlatformAccessUsers.user_ids).toHaveLength(101);
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
  const details = document.querySelector<HTMLDetailsElement>('[role="dialog"] details')!;
  expect(details.open).toBe(false);
  expect(details.querySelector("summary")?.textContent).toContain("rework.platformAccess.activation.unverified");
  expect(details.textContent).toContain("Unverified");
  const summary = details.querySelector("summary")!;
  summary.focus();
  act(() => summary.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })));
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
  expect(dialog.querySelector("details")).toBeNull();
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
