// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, useState } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
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
  configured: true,
  filter: vi.fn(() => ({ unwrap: async () => undefined })),
  bulk: vi.fn((_arg: { grantPlatformAccessUsers: { user_ids: string[] } }) => ({ unwrap: async () => undefined })),
  grant: vi.fn(() => ({ unwrap: async () => undefined })),
  importT0: vi.fn(() => ({ unwrap: async () => undefined })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("../../../../../common/config", () => ({ getConfig: () => ({ platform_access_enabled: true }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessStateQuery: () => ({
    data: { filtering_enabled: false, revision: 1, has_admission_sources: state.configured },
  }),
  usePlatformAccessActivationPreviewQuery: () => ({
    data: { revision: 1, allowed: 1, blocked: 0, unknown: 0, checked_at: "2026-10-08T12:00:00Z", users: [] },
  }),
  usePlatformAccessUsersQuery: () => ({
    data: {
      total: state.users.length,
      items: state.users,
    },
  }),
  usePlatformAccessT0Query: () => ({
    data: { candidates: 1, matching: 0, completed_at: state.completed ? "2026-01-01" : null },
  }),
  usePlatformAccessTeamsQuery: () => ({
    data: [{ team_id: "demo", name: "Demo", allowed: false, free: true, has_enrollment_link: true }],
  }),
  useSetPlatformFilteringMutation: () => [state.filter],
  useGrantPlatformUsersMutation: () => [state.bulk],
  useGrantPlatformUserMutation: () => [state.grant],
  useRevokePlatformUserMutation: () => [vi.fn()],
  useImportPlatformT0Mutation: () => [state.importT0],
  useSetPlatformTeamMutation: () => [vi.fn()],
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
const render = () => {
  act(() => root.render(<PlatformAccessPage />));
  openTab("users");
};

it("exposes only the selected panel and supports keyboard section navigation", () => {
  act(() => root.render(<PlatformAccessPage />));
  const tabs = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  const panels = [...host.querySelectorAll<HTMLDivElement>('[role="tabpanel"]')];
  expect(tabs).toHaveLength(4);
  expect(panels.filter((panel) => !panel.hidden)).toEqual([panels[0]]);
  expect(panels[0].getAttribute("aria-labelledby")).toBe(tabs[0].id);
  expect(tabs[0].getAttribute("aria-controls")).toBe(panels[0].id);
  act(() => tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
  expect(document.activeElement).toBe(tabs[1]);
  expect(tabs[1].getAttribute("aria-selected")).toBe("true");
  expect(panels.filter((panel) => !panel.hidden)).toEqual([panels[1]]);
  openTab("activation");
  expect(panels.filter((panel) => !panel.hidden)).toEqual([panels[3]]);
  expect(
    [...host.querySelectorAll("button")].find((node) => node.textContent === "rework.platformAccess.activation.enable"),
  ).toBeDefined();
});

it("preserves rule drafts and user selections across tabs without mutations", async () => {
  act(() => root.render(<PlatformAccessPage />));
  act(() => [...host.querySelectorAll("button")].find((node) => node.textContent === "Edit draft")!.click());
  openTab("users");
  const selection = host.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.selectUser"]')!;
  await act(async () => selection.click());
  openTab("teams");
  openTab("rules");
  expect(host.querySelector('[role="tabpanel"]:not([hidden])')?.textContent).toContain("Unsaved rule");
  openTab("users");
  expect(selection.checked).toBe(true);
  expect(state.bulk).not.toHaveBeenCalled();
  expect(state.grant).not.toHaveBeenCalled();
  expect(state.importT0).not.toHaveBeenCalled();
});
it("shows Free team provenance and offers an independent individual grant", async () => {
  render();
  expect(host.textContent).toContain("rework.platformAccess.source.free: Demo");
  const button = [...host.querySelectorAll("button")].find(
    (node) => node.textContent === "rework.platformAccess.allow",
  )!;
  await act(async () => button.click());
  expect(state.grant).toHaveBeenCalledWith({ userId: "user" });
});
it("makes the completed initial import immutable", () => {
  state.completed = true;
  render();
  const button = [...host.querySelectorAll("button")].find((node) =>
    node.textContent?.includes("rework.platformAccess.t0Done"),
  )!;
  expect(button.disabled).toBe(true);
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
  expect(action().disabled).toBe(true);
  state.configured = true;
  render();
  for (const tab of ["rules", "users", "teams", "activation"]) {
    openTab(tab);
    expect(action().disabled).toBe(false);
  }
  act(() => action().click());
  expect(state.filter).not.toHaveBeenCalled();
  const dialog = document.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("rework.platformAccess.activation.summary");
  act(() => [...dialog.querySelectorAll("button")].find((node) => node.textContent === "common.cancel")!.click());
  expect(state.filter).not.toHaveBeenCalled();
  act(() => action().click());
  await act(async () =>
    [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')]
      .find((node) => node.textContent === "rework.platformAccess.activation.enable")!
      .click(),
  );
  expect(state.filter).toHaveBeenCalledWith({
    setPlatformFiltering: { filtering_enabled: true, expected_revision: 1 },
  });
});
