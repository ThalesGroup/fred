// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ImportBlueprintApiResponse } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const h = vi.hoisted(() => ({
  access: { isAdmin: true, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() },
  result: {
    isLoading: false,
    isSuccess: false,
    error: undefined as unknown,
    data: undefined as ImportBlueprintApiResponse | undefined,
    reset: vi.fn(),
  },
  submit: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => h.access }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useImportBlueprintMutation: () => [h.submit, h.result],
}));
import ProvisioningPage from "./ProvisioningPage";
let container: HTMLDivElement;
let root: Root;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function render() {
  act(() => root.render(<ProvisioningPage />));
}
function selectFile() {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["zip"], "demo.zip", { type: "application/zip" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  act(() => input.dispatchEvent(new Event("change", { bubbles: true })));
  return file;
}
beforeEach(() => {
  Object.assign(h.access, { isAdmin: true, isLoading: false, isFetching: false, isError: false });
  Object.assign(h.result, { isLoading: false, isSuccess: false, error: undefined, data: undefined });
  vi.clearAllMocks();
  h.submit.mockResolvedValue({ data: {} });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("ProvisioningPage", () => {
  it.each(["loading", "forbidden", "unavailable"])("hides the upload when authority is %s", (state) => {
    h.access.isLoading = state === "loading";
    h.access.isError = state === "unavailable";
    h.access.isAdmin = false;
    render();
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(container.textContent).toContain(
      state === "loading"
        ? "common.loading"
        : state === "forbidden"
          ? "rework.provisioning.forbidden"
          : "rework.provisioning.authorityUnavailable",
    );
    if (state === "unavailable") {
      act(() => container.querySelector("button")!.click());
      expect(h.access.refetch).toHaveBeenCalledOnce();
    }
  });
  it("submits the selected File once even if submit events arrive before rerender", async () => {
    let resolve: (value: unknown) => void;
    h.submit.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    render();
    expect((container.querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
    const file = selectFile();
    act(() => {
      container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(h.submit).toHaveBeenCalledExactlyOnceWith({ provisioningUpload: { file } });
    h.result.isLoading = true;
    render();
    expect((container.querySelector("fieldset") as HTMLFieldSetElement).disabled).toBe(true);
    expect(container.querySelector('[role="status"]')?.textContent).toContain("rework.provisioning.pending");
    await act(async () => resolve!({ data: {} }));
  });
  it("shows only server counts after success and resets the report when selecting another file", () => {
    h.result.isSuccess = true;
    h.result.data = { identities_resolved: 15, identities_created: 0, spaces_reconciled: 5, grants_acknowledged: 44 };
    render();
    expect([...container.querySelectorAll("dd")].map((node) => node.textContent)).toEqual(["15", "0", "5", "44"]);
    selectFile();
    expect(h.result.reset).toHaveBeenCalledOnce();
  });
  it.each([
    [{ status: 422, data: { detail: "not_yet_supported" } }, "rework.provisioning.unsupported"],
    [{ status: 401, data: { detail: "partial import: identities_created=2" } }, "partial import: identities_created=2"],
    [{ status: "FETCH_ERROR", error: "network unavailable" }, "rework.provisioning.networkError"],
  ])("presents failure and replay guidance without a success report", (error, message) => {
    h.result.error = error;
    render();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(message);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("rework.provisioning.replay");
    expect(container.querySelector("dl")).toBeNull();
    expect(h.submit).not.toHaveBeenCalled();
  });
});
