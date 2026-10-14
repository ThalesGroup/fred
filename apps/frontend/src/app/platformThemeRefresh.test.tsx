// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { configureStore } from "@reduxjs/toolkit";
import { act, useContext } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { enhancedControlPlaneApi as api } from "../slices/controlPlane/controlPlaneApiEnhancements";
import type { FrontendUiThemes } from "../slices/controlPlane/controlPlaneOpenApi";
import { localStorageKey } from "../hooks/useLocalStorageState";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import { PLATFORM_UI_THEMES_CACHE_KEY, setCustomUiThemes, UI_THEME_STORAGE_KEY } from "./uiThemes";
vi.mock("../common/config.tsx", () => ({
  getPlatformUiThemes: () => ({ default_theme: "pebble", hidden_themes: [] }),
}));
vi.mock("../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "test", ensureFreshToken: async () => true, CallLogout: () => {} },
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const makeStore = () =>
  configureStore({ reducer: { [api.reducerPath]: api.reducer }, middleware: (g) => g().concat(api.middleware) });
let store: ReturnType<typeof makeStore>, root: Root, host: HTMLDivElement, settings: FrontendUiThemes;
let fail = false,
  publicRequests = 0;
const publicPath = "/control-plane/v1/frontend/config",
  adminPath = "/control-plane/v1/admin/platform/ui-settings";
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
beforeEach(() => {
  settings = { default_theme: "cloud", hidden_themes: [] };
  fail = false;
  publicRequests = 0;
  window.localStorage.clear();
  window.localStorage.setItem(localStorageKey(UI_THEME_STORAGE_KEY), JSON.stringify("acme"));
  setCustomUiThemes([{ id: "acme", label: "Acme", base: "cobalt" }]);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === publicPath) {
        publicRequests++;
        return fail ? response({}, 503) : response({ ui_themes: settings });
      }
      if (path === adminPath && input.method === "PUT") {
        settings = await input.json();
        return response(settings);
      }
      throw new Error(`Unexpected test request ${path}`);
    }),
  );
  store = makeStore();
  host = document.createElement("div");
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  store.dispatch(api.util.resetApiState());
  setCustomUiThemes([]);
  window.localStorage.clear();
  vi.unstubAllGlobals();
});
async function mount() {
  function Probe() {
    const { uiTheme, offeredUiThemes } = useContext(ApplicationContext);
    return (
      <>
        <output>{uiTheme}</output>
        <select>
          {offeredUiThemes.map((id) => (
            <option key={id}>{id}</option>
          ))}
        </select>
      </>
    );
  }
  await act(async () => {
    root.render(
      <Provider store={store}>
        <ApplicationContextProvider>
          <Probe />
        </ApplicationContextProvider>
      </Provider>,
    );
  });
  await act(async () => {
    await vi.waitFor(() => expect(publicRequests).toBeGreaterThan(0));
  });
}
const active = () => host.querySelector("output")?.textContent;
const offered = () => Array.from(host.querySelectorAll("option"), (o) => o.textContent);
it("a real admin save hides the active theme and selects the admin default", async () => {
  await mount();
  expect(active()).toBe("acme");
  await act(async () => {
    await store
      .dispatch(
        api.endpoints.putPlatformUiSettingsControlPlaneV1AdminPlatformUiSettingsPut.initiate({
          setPlatformUiSettingsRequest: { default_theme: "cloud", hidden_themes: ["acme", "cobalt"] },
        }),
      )
      .unwrap();
    await vi.waitFor(() => expect(active()).toBe("cloud"));
  });
  expect(offered()).toEqual(["pebble", "cloud"]);
  expect(JSON.parse(window.localStorage.getItem(PLATFORM_UI_THEMES_CACHE_KEY)!)).toEqual(settings);
  expect(JSON.parse(window.localStorage.getItem(localStorageKey(UI_THEME_STORAGE_KEY))!)).toBe("acme");
});
it("focus receives external settings and a failed refresh retains them", async () => {
  await mount();
  settings = { default_theme: "acme", hidden_themes: ["pebble", "cobalt", "cloud"] };
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
    await vi.waitFor(() => expect(offered()).toEqual(["acme"]));
  });
  expect(active()).toBe("acme");
  fail = true;
  const before = publicRequests;
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
    await vi.waitFor(() => expect(publicRequests).toBeGreaterThan(before));
    await vi.waitFor(() =>
      expect(api.endpoints.getFrontendConfigControlPlaneV1FrontendConfigGet.select()(store.getState()).isError).toBe(
        true,
      ),
    );
  });
  expect(offered()).toEqual(["acme"]);
  expect(active()).toBe("acme");
});
it("a removed catalog theme falls back to the offered admin default", async () => {
  setCustomUiThemes([]);
  await mount();
  await act(async () => {
    await vi.waitFor(() => expect(active()).toBe("cloud"));
  });
  expect(offered()).toEqual(["pebble", "cobalt", "cloud"]);
});
