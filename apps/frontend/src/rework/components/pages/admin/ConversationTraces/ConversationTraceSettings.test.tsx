// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { configureStore } from "@reduxjs/toolkit";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import ConversationTraceListPage from "./ConversationTraceListPage";
import ConversationTraceSettingsPage from "./ConversationTraceSettings";
import { TRACE_LIST_PATH } from "./traceControls";

const tracePath = "/control-plane/v1/organizations/organization/conversation-traces";
const settingsPath = TRACE_LIST_PATH + "/settings";
const saved = vi.fn();

vi.mock("@core/hooks/useConversationTraceAccess", () => ({
  useConversationTraceAccess: () => ({
    organizationId: "organization",
    canRead: true,
    canManage: true,
    isLoading: false,
  }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../../common/dynamicBaseQuery", () => ({
  createDynamicBaseQuery:
    () =>
    async ({ url, method, body }: { url: string; method?: string; body?: unknown }) => {
      if (url === tracePath + "/settings") {
        if (method === "PUT") saved(body);
        return {
          data: {
            enabled: true,
            degraded: false,
            reserved_bytes: 0,
            retention_days: 30,
            sampling_percent: 100,
            storage_cap_bytes: 2_000_000_000,
            used_bytes: 500_000_000,
          },
        };
      }
      if (url === tracePath + "/teams") return { data: [] };
      return { data: { conversations: [], next_cursor: null } };
    },
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let cleanup: (() => void) | undefined;
afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  saved.mockReset();
});

async function render(initialPath: string, routes: { path: string; element: ReactNode }[]) {
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () =>
    root.render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    ),
  );
  await act(async () => {
    await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
  });
  cleanup = () => {
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
  };
  return { host, router };
}

function type(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

it("shows capture settings as a page with text limit fields and saves the changed limit", async () => {
  const { host } = await render(settingsPath, [{ path: settingsPath, element: <ConversationTraceSettingsPage /> }]);

  expect(host.querySelector('[role="dialog"], dialog')).toBeNull();
  expect(host.querySelector("h1")?.textContent).toBe("captureSettings");
  expect(host.querySelector("meter")).not.toBeNull();
  const inputs = [...host.querySelectorAll<HTMLInputElement>("input:not([type=checkbox])")];
  expect(inputs.map((input) => [input.type, input.inputMode, input.value])).toEqual([
    ["text", "decimal", "2"],
    ["text", "numeric", "30"],
    ["text", "numeric", "100"],
  ]);

  await act(async () => type(inputs[0], "1,5"));
  const save = [...host.querySelectorAll("button")].find((button) => button.textContent === "saveLimits")!;
  expect(save.disabled).toBe(false);
  await act(async () => save.click());
  expect(saved).toHaveBeenCalledWith({ storage_cap_bytes: 1_500_000_000 });
});

it("opens the capture settings page from the trace list", async () => {
  const { host, router } = await render(TRACE_LIST_PATH, [
    { path: TRACE_LIST_PATH, element: <ConversationTraceListPage /> },
    { path: settingsPath, element: <ConversationTraceSettingsPage /> },
  ]);

  const settings = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes("settings"))!;
  await act(async () => settings.click());
  expect(router.state.location.pathname).toBe(settingsPath);
});
