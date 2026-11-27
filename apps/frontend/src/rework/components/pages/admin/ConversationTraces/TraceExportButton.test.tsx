// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { TraceExportButton } from "./TraceExportButton";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "test-token" },
}));
vi.mock("../../../../../common/platformAccess", () => ({
  handlePlatformAccessResponse: vi.fn(),
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it.each([
  { sessionIds: ["masked"], hasSharedContent: false, mode: "masked_content" },
  { sessionIds: ["shared"], hasSharedContent: true, mode: "shared_content" },
  { sessionIds: ["masked", "another-masked"], hasSharedContent: false, mode: "shared_content" },
])("requires a direct export choice for $sessionIds", async ({ sessionIds, hasSharedContent, mode }) => {
  const fetchZip = vi.fn(async () => new Response(null, { status: 409 }));
  vi.stubGlobal("fetch", fetchZip);
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  try {
    await act(async () =>
      root.render(<TraceExportButton sessionIds={sessionIds} hasSharedContent={hasSharedContent} />),
    );
    await act(async () => host.querySelector("button")!.click());
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    expect(document.activeElement).toBe(dialog);
    await act(async () => dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(fetchZip).not.toHaveBeenCalled();

    const buttons = [...dialog.querySelectorAll<HTMLButtonElement>("button")];
    expect(buttons.map((button) => button.textContent)).toEqual([
      "exportMode.masked_content.label",
      "exportMode.shared_content.label",
      "cancel",
    ]);
    expect(dialog.querySelector('input[type="radio"]')).toBeNull();
    const [masked, full] = buttons;
    expect(masked.disabled).toBe(false);
    expect(full.disabled).toBe(mode === "masked_content");
    if (full.disabled) {
      expect(document.getElementById(full.getAttribute("aria-describedby")!)?.textContent).toBe(
        "exportFullUnavailable",
      );
      await act(async () => full.click());
      expect(fetchZip).not.toHaveBeenCalled();
    }
    await act(async () => (mode === "masked_content" ? masked : full).click());
    expect(fetchZip).toHaveBeenCalledExactlyOnceWith(
      "/control-plane/v1/admin/conversation-traces/export",
      expect.objectContaining({ body: JSON.stringify({ session_ids: sessionIds, mode }) }),
    );
    expect(dialog.querySelector('[role="alert"]')?.textContent).toBe("exportChanged");
  } finally {
    act(() => root.unmount());
    host.remove();
    vi.unstubAllGlobals();
  }
});
