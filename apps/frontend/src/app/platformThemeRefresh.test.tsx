// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act, useContext } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { localStorageKey } from "../hooks/useLocalStorageState";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import { PLATFORM_UI_THEMES_CACHE_KEY, setCustomUiThemes, UI_THEME_STORAGE_KEY } from "./uiThemes";
vi.mock("../common/config.tsx", () => ({
  getPlatformUiThemes: () => ({ default_theme: "cloud", hidden_themes: [] }),
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let root: Root, host: HTMLDivElement;
beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(localStorageKey(UI_THEME_STORAGE_KEY), JSON.stringify("acme"));
  setCustomUiThemes([{ id: "acme", label: "Acme", base: "cobalt" }]);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("Unexpected presentation request");
    }),
  );
  host = document.createElement("div");
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  setCustomUiThemes([]);
  window.localStorage.clear();
  vi.unstubAllGlobals();
});
function mount() {
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
  act(() =>
    root.render(
      <ApplicationContextProvider>
        <Probe />
      </ApplicationContextProvider>,
    ),
  );
}
it("uses startup presentation configuration and the user's theme without Python subscriptions", () => {
  mount();
  expect(host.querySelector("output")?.textContent).toBe("acme");
  act(() => window.dispatchEvent(new Event("focus")));
  expect(fetch).not.toHaveBeenCalled();
  expect(JSON.parse(window.localStorage.getItem(PLATFORM_UI_THEMES_CACHE_KEY)!)).toEqual({
    default_theme: "cloud",
    hidden_themes: [],
  });
});
it("falls back to the configured theme if the stored theme leaves the catalog", () => {
  setCustomUiThemes([]);
  mount();
  expect(host.querySelector("output")?.textContent).toBe("cloud");
  expect(Array.from(host.querySelectorAll("option"), (o) => o.textContent)).toEqual(["pebble", "cobalt", "cloud"]);
});
