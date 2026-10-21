// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import SelfTestPage from "./SelfTestPage";
const h = vi.hoisted(() => ({ first: vi.fn(), second: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("./AuthorizationExtras", () => ({ AuthorizationExtras: () => null }));
vi.mock("./FamilySection", () => ({ FamilySection: () => null }));
vi.mock("../../../../features/pipeline/families", () => ({
  useSelfTestFamilies: () => [
    { id: "platform", run: { isRunning: false, steps: [], start: h.first } },
    { id: "teams", run: { isRunning: false, steps: [], start: h.second } },
  ],
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
it("does not start further families after leaving the page, while the current teardown finishes", async () => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let cleaned = false;
  h.first.mockImplementation(async () => {
    try {
      await pending;
    } finally {
      cleaned = true;
    }
  });
  h.second.mockResolvedValue(undefined);
  const container = document.createElement("div"),
    root = createRoot(container);
  document.body.appendChild(container);
  act(() => root.render(<SelfTestPage />));
  const button = Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("rework.selftest.page.runAll"),
  )!;
  act(() => button.click());
  expect(h.first).toHaveBeenCalledOnce();
  act(() => root.unmount());
  await act(async () => {
    release();
    await pending;
  });
  expect(cleaned).toBe(true);
  expect(h.second).not.toHaveBeenCalled();
  container.remove();
});
