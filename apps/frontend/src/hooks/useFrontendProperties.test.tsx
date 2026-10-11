// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { useFrontendProperties } from "./useFrontendProperties";
vi.mock("../common/config", () => ({
  getProperty: (key: string) => (key === "contactSupportLink" ? "https://support.example.test/help" : undefined),
  getGcuVersion: () => null,
  getRootBootstrapRequired: () => false,
  getConfig: () => {
    throw new Error("Protected/public backend state is unavailable");
  },
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
it("exposes the shared static support destination before backend bootstrap", () => {
  function Consumer() {
    const { contactSupportLink } = useFrontendProperties();
    return <a href={contactSupportLink}>Support</a>;
  }
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    act(() => root.render(<Consumer />));
    expect(host.querySelector("a")!.href).toBe("https://support.example.test/help");
  } finally {
    act(() => root.unmount());
  }
});
