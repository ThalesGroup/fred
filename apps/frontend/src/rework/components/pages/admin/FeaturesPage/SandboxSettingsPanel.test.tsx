// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  save: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  refetch: vi.fn(() => Promise.resolve()),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetSandboxSettingsControlPlaneV1AdminPlatformSandboxSettingsGetQuery: () => ({
    data: {
      idle_minutes: 20,
      max_active_sessions: 8,
      warm_capacity: 0,
      profile_id: "gvisor-approved",
    },
    isLoading: false,
    isError: false,
    refetch: h.refetch,
  }),
  usePutSandboxSettingsControlPlaneV1AdminPlatformSandboxSettingsPutMutation: () => [h.save, { isLoading: false }],
}));

import { SandboxSettingsPanel } from "./SandboxSettingsPanel";

let root: Root;
let container: HTMLDivElement;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  h.save.mockClear();
  h.refetch.mockClear();
});

it("shows only approved profile and three controls, then saves bounded settings", async () => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<SandboxSettingsPanel visible />));
  expect(container.textContent).toContain("gvisor-approved");
  expect(container.querySelectorAll('input[type="number"]')).toHaveLength(3);
  expect(container.querySelector('input[name="runtime"]')).toBeNull();
  const saveButton = Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("rework.admin.sandboxSettings.save"),
  );
  expect(saveButton).toBeDefined();
  await act(async () => {
    saveButton?.click();
  });
  expect(h.save).toHaveBeenCalledWith({
    sandboxSettingsUpdate: {
      idle_minutes: 20,
      max_active_sessions: 8,
      warm_capacity: 0,
    },
  });
});
