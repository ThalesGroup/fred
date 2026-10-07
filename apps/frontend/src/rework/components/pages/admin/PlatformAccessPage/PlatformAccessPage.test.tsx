// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
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
  bulk: vi.fn((_arg: { grantPlatformAccessUsers: { user_ids: string[] } }) => ({ unwrap: async () => undefined })),
  grant: vi.fn(() => ({ unwrap: async () => undefined })),
  importT0: vi.fn(() => ({ unwrap: async () => undefined })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("../../../../../common/config", () => ({ getConfig: () => ({ platform_access_enabled: true }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessStateQuery: () => ({ data: { filtering_enabled: false } }),
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
  useSetPlatformFilteringMutation: () => [vi.fn()],
  useGrantPlatformUsersMutation: () => [state.bulk],
  useGrantPlatformUserMutation: () => [state.grant],
  useRevokePlatformUserMutation: () => [vi.fn()],
  useImportPlatformT0Mutation: () => [state.importT0],
  useSetPlatformTeamMutation: () => [vi.fn()],
  useGeneratePlatformLinkMutation: () => [vi.fn()],
}));
vi.mock("./PlatformAccessRuleEditor", () => ({ default: () => <div>Rule editor</div> }));
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
  vi.clearAllMocks();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const render = () => act(() => root.render(<PlatformAccessPage />));
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

it("caps selection at 100 before dispatching a bulk grant", async () => {
  state.users = Array.from({ length: 101 }, (_, index) => ({
    user_id: `user-${index}`,
    username: `User ${index}`,
    email: "",
    sources: [],
  }));
  render();
  const choices = [...host.querySelectorAll<HTMLInputElement>('input[aria-label="rework.platformAccess.selectUser"]')];
  for (const choice of choices) await act(async () => choice.click());
  expect(choices.filter((choice) => choice.checked)).toHaveLength(100);
  expect(choices[100].disabled).toBe(true);
  await act(async () =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.allowSelected")!
      .click(),
  );
  expect(state.bulk.mock.calls[0][0].grantPlatformAccessUsers.user_ids).toHaveLength(100);
});
