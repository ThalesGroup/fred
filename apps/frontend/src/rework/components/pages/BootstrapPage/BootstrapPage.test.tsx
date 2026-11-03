// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";

const { logout, claim } = vi.hoisted(() => ({ logout: vi.fn(), claim: vi.fn() }));
vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { CallLogout: logout } }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useBootstrapPlatformAdminMutation: () => [claim, { isLoading: false }],
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { username: string }) => (values ? `${key}: ${values.username}` : key),
  }),
}));
import BootstrapPage from "./BootstrapPage";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
it("identifies the SSO account and lets the installer leave it without claiming administration", () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    act(() => root.render(<BootstrapPage username="PN" />));
    expect(host.textContent).toContain("rework.bootstrap.connectedAs: PN");
    const buttons = [...host.querySelectorAll("button")];
    const submit = buttons.find((button) => button.textContent === "rework.bootstrap.submit")!;
    expect(submit.disabled).toBe(true);
    act(() => buttons.find((button) => button.textContent === "rework.bootstrap.changeAccount")!.click());
    expect(logout).toHaveBeenCalledOnce();
    expect(claim).not.toHaveBeenCalled();
  } finally {
    act(() => root.unmount());
  }
});
