// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  version: "v1" as string | null,
  bootstrap: true,
  legalFailed: false,
  accepted: false,
  failStatus: false,
  failConsent: false,
  calls: [] as string[],
}));
vi.mock("../common/config", () => ({ getConfig: () => ({ frontend_basename: "/" }) }));
vi.mock("../security/KeycloakService", () => ({
  KeyCloakService: { CallLogout: vi.fn(), GetUserFullName: () => "Alice", GetUserMail: () => "alice@example.test" },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("./ApplicationContextProvider", async () => {
  const { createContext } = await import("react");
  return {
    ApplicationContext: createContext({ darkMode: false, uiTheme: "pebble" }),
    ApplicationThemeProvider: ({ children }) => children,
  };
});
vi.mock("@hooks/useLegalMarkdown.ts", async () => {
  const { useState } = await import("react");
  return {
    useLegalMarkdownState: () => ({
      markdown: useState(() => (state.legalFailed ? "" : `Terms ${state.version}`))[0],
      failed: state.legalFailed,
    }),
  };
});
vi.mock("../hooks/useFrontendProperties.ts", () => ({ useFrontendProperties: () => ({ gcuVersion: "v1" }) }));
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }) => <p>{text}</p>,
}));
vi.mock("@components/pages/BootstrapPage/BootstrapPage", () => ({ default: () => <p>Root bootstrap</p> }));
vi.mock("../common/dynamicBaseQuery", () => ({
  createDynamicBaseQuery: () => async (request) => {
    state.calls.push(request.url);
    if (request.url.endsWith("/me/onboarding")) {
      return state.failStatus
        ? { error: { status: 503, data: { detail: "unavailable" } } }
        : {
            data: {
              user_id: "alice",
              username: "alice",
              gcu_version: state.version,
              acceptance: state.accepted ? { version: "v1", accepted_at: "2026-10-15T00:00:00Z" } : null,
              root_bootstrap_required: state.bootstrap,
            },
          };
    }
    if (request.url.endsWith("/gcu")) {
      expect(request.body).toEqual({ version: "v1" });
      if (state.failConsent) return { error: { status: 409, data: { detail: "gcu_version_changed" } } };
      state.accepted = true;
      return { data: null };
    }
    throw new Error(`Unexpected business request before onboarding: ${request.url}`);
  },
}));
import { MemoryRouter } from "react-router-dom";
import GcuGuard from "@core/guards/GcuGuard";
import BootstrapGuard from "@core/guards/BootstrapGuard";
import { KeyCloakService } from "../security/KeycloakService";
import { enhancedFredManagerApi as api } from "../slices/fredManager/fredManagerApiEnhancements";
import { controlPlaneApi } from "../slices/controlPlane/controlPlaneApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => {
  state.version = "v1";
  state.bootstrap = true;
  vi.clearAllMocks();
  state.legalFailed = false;
  state.accepted = false;
  state.failStatus = false;
  state.failConsent = false;
  state.calls = [];
  vi.unstubAllGlobals();
});

async function mounted(run: (host: HTMLDivElement) => Promise<void>) {
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
    reducer: { [api.reducerPath]: api.reducer, [controlPlaneApi.reducerPath]: controlPlaneApi.reducer },
    middleware: (defaults) => defaults().concat(api.middleware, controlPlaneApi.middleware),
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <MemoryRouter>
            <GcuGuard>
              <BootstrapGuard>
                <p>Admitted</p>
              </BootstrapGuard>
            </GcuGuard>
          </MemoryRouter>
        </Provider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    await run(host);
  } finally {
    act(() => root.unmount());
    store.dispatch(api.util.resetApiState());
    store.dispatch(controlPlaneApi.util.resetApiState());
    host.remove();
  }
}
async function click(host: HTMLDivElement, text: string) {
  await act(async () => {
    [...host.querySelectorAll("button")].find((button) => button.textContent?.includes(text))!.click();
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

// Proves: I19
it("keeps business queries unmounted until consent and root bootstrap are complete", async () => {
  await mounted(async (host) => {
    expect(host.textContent).toContain("rework.gcu.validate");
    expect(host.textContent).not.toContain("Root bootstrap");
    await click(host, "rework.gcu.validate");
    expect(host.textContent).toContain("Root bootstrap");
    expect(host.textContent).not.toContain("rework.gcu.validate");
    expect(state.calls).toEqual([
      "/fred-manager/v1/me/onboarding",
      "/fred-manager/v1/gcu",
      "/fred-manager/v1/me/onboarding",
    ]);
  });
});

// Proves: I19
it("an unavailable onboarding service fails closed and can be retried", async () => {
  state.failStatus = true;
  await mounted(async (host) => {
    expect(host.querySelector('[role="alert"]')).not.toBeNull();
    expect(host.textContent).not.toContain("Root bootstrap");
    expect(host.textContent).not.toContain("rework.gcu.validate");
    state.failStatus = false;
    await click(host, "rework.provisioning.retryAuthority");
    expect(host.textContent).toContain("rework.gcu.validate");
  });
});

// Proves: I19
it("a stale consent submission never advances the journey or assumes success", async () => {
  state.failConsent = true;
  await mounted(async (host) => {
    await click(host, "rework.gcu.validate");
    expect(host.querySelector('[role="alert"]')).not.toBeNull();
    expect(host.textContent).not.toContain("Root bootstrap");
    expect(state.accepted).toBe(false);
    expect(state.calls).toEqual(["/fred-manager/v1/me/onboarding", "/fred-manager/v1/gcu"]);
  });
});

// Proves: I19
it("refreshing the active version reloads the legal document before consent", async () => {
  await mounted(async (host) => {
    expect(host.textContent).toContain("Terms v1");
    state.version = "v2";
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(host.textContent).toContain("Terms v2");
    expect(host.textContent).not.toContain("Terms v1");
    expect(state.accepted).toBe(false);
    expect(state.calls).toEqual(["/fred-manager/v1/me/onboarding", "/fred-manager/v1/me/onboarding"]);
  });
});

// Proves: I19
it("missing legal text exposes retry and never enables consent", async () => {
  state.legalFailed = true;
  await mounted(async (host) => {
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("rework.gcu.unavailable");
    const accept = [...host.querySelectorAll("button")].find((button) => button.textContent === "rework.gcu.validate")!;
    expect(accept.disabled).toBe(true);
    expect(host.textContent).not.toContain("Root bootstrap");
    expect(state.calls).toEqual(["/fred-manager/v1/me/onboarding"]);
  });
});

it("allows disabled terms only after status confirms bootstrap completion", async () => {
  state.version = null;
  state.bootstrap = false;
  await mounted(async (host) => {
    expect(host.textContent).toContain("Admitted");
    expect(state.calls).toEqual(["/fred-manager/v1/me/onboarding"]);
  });
});

it.each(["terms", "bootstrap", "failure"])(
  "keeps identity/logout available during %s without business queries",
  async (phase) => {
    state.accepted = phase === "bootstrap";
    state.failStatus = phase === "failure";
    await mounted(async (host) => {
      await act(async () => {
        host.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')!.click();
      });
      expect(host.textContent).toContain("alice@example.test");
      await click(host, "rework.userSettings.disconnect");
      expect(KeyCloakService.CallLogout).toHaveBeenCalledOnce();
      expect(state.calls).toEqual(["/fred-manager/v1/me/onboarding"]);
    });
  },
);

// Proves: I19
it("gates an admitted view again after a changed version or failed status refresh", async () => {
  state.accepted = true;
  state.bootstrap = false;
  await mounted(async (host) => {
    expect(host.textContent).toContain("Admitted");
    state.version = "v2";
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(host.textContent).not.toContain("Admitted");
    expect(host.textContent).toContain("Terms v2");
    state.failStatus = true;
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(host.querySelector('[role="alert"]')).not.toBeNull();
    expect(host.textContent).not.toContain("rework.gcu.validate");
  });
});
