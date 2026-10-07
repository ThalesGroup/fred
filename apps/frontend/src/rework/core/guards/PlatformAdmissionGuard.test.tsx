// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ accepted: false, statusReads: 0, failed: false }));
vi.mock("../../../common/dynamicBaseQuery", () => ({
  createDynamicBaseQuery: () => async (request: { url: string; method?: string }) => {
    if (request.url.endsWith("/platform-access/status")) {
      state.statusReads++;
      if (state.failed) return { error: { status: 503, data: { detail: "platform_access_unavailable" } } };
      return { data: { admitted: true, cgu_required: !state.accepted } };
    }
    if (request.url.endsWith("/gcu")) {
      state.accepted = true;
      return { data: {} };
    }
    return { data: { cguValidated: state.accepted ? "v1" : null } };
  },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../hooks/useFrontendProperties", () => ({ useFrontendProperties: () => ({ gcuVersion: "v1" }) }));
vi.mock("@hooks/useLegalMarkdown.ts", () => ({ useLegalMarkdown: () => "Terms of use" }));
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({ MarkdownRenderer: () => <p>Terms of use</p> }));
import { enhancedControlPlaneApi } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import PlatformAdmissionGuard from "./PlatformAdmissionGuard";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("accepting CGU refreshes admission and opens the protected shell outside router context", async () => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private callback: (entries: unknown[]) => void) {}
      observe(target: Element) {
        this.callback([{ isIntersecting: true, target }]);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <PlatformAdmissionGuard>
            <p>Protected shell</p>
          </PlatformAdmissionGuard>
        </Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(host.textContent).toContain("rework.gcu.title");
    const accept = [...host.querySelectorAll("button")].find((button) => button.textContent === "rework.gcu.validate")!;
    expect(accept.disabled).toBe(false);
    await act(async () => {
      accept.click();
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(state.statusReads).toBeGreaterThan(1);
    expect(host.textContent).toContain("Protected shell");
    expect(host.textContent).not.toContain("rework.gcu.title");
  } finally {
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
    vi.unstubAllGlobals();
  }
});

it("renders shared verification failure outside the router and retries without mounting protected content", async () => {
  state.failed = true;
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <PlatformAdmissionGuard>
            <p>Protected shell</p>
          </PlatformAdmissionGuard>
        </Provider>,
      );
      await new Promise((done) => setTimeout(done, 20));
    });
    expect(host.querySelector("h1")?.textContent).toBe("rework.platformAccess.verificationFailed");
    expect(host.textContent).not.toContain("Protected shell");
    const before = state.statusReads;
    const retry = [...host.querySelectorAll("button")].find(
      (node) => node.textContent === "rework.platformAccess.retry",
    )!;
    await act(async () => {
      retry.click();
      await new Promise((done) => setTimeout(done, 20));
    });
    expect(state.statusReads).toBeGreaterThan(before);
  } finally {
    state.failed = false;
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
  }
});
