// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({
  completed: false,
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
      total: 1,
      items: [
        {
          user_id: "user",
          username: "Alice",
          email: "alice@example.org",
          sources: [{ kind: "free", team_id: "demo", team_name: "Demo" }],
        },
      ],
    },
  }),
  usePlatformAccessT0Query: () => ({
    data: { candidates: 1, matching: 0, completed_at: state.completed ? "2026-01-01" : null },
  }),
  usePlatformAccessTeamsQuery: () => ({
    data: [{ team_id: "demo", name: "Demo", allowed: false, free: true, has_enrollment_link: true }],
  }),
  useSetPlatformFilteringMutation: () => [vi.fn()],
  useGrantPlatformUserMutation: () => [state.grant],
  useRevokePlatformUserMutation: () => [vi.fn()],
  useImportPlatformT0Mutation: () => [state.importT0],
  useSetPlatformTeamMutation: () => [vi.fn()],
  useGeneratePlatformLinkMutation: () => [vi.fn()],
}));
import PlatformAccessPage from "./PlatformAccessPage";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
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
  const button = [...host.querySelectorAll("button")].find((node) =>
    node.textContent?.includes("rework.platformAccess.allow"),
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
