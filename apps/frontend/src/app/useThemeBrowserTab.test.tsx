// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { ApplicationContext } from "./ApplicationContextProvider";
import { setCustomUiThemes } from "./uiThemes";
import { useThemeBrowserTab } from "./useThemeBrowserTab";
vi.mock("../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ siteDisplayName: "Fred", faviconName: "fred", faviconNameDark: "fred-dark" }),
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => setCustomUiThemes([]));
it("updates the tab on theme/mode changes and restores stock branding", () => {
  setCustomUiThemes([
    {
      id: "paris",
      label: "Paris",
      base: "cobalt",
      tabTitle: "Paris Aéroport",
      faviconName: "paris-light",
      faviconNameDark: "paris-dark",
    },
    { id: "single", label: "Single", base: "cloud", faviconName: "single-icon" },
  ]);
  const favicon = document.createElement("link");
  favicon.id = "favicon";
  document.head.append(favicon);
  const root = createRoot(document.createElement("div"));
  const Probe = () => {
    useThemeBrowserTab();
    return null;
  };
  const render = (uiTheme: string, darkMode: boolean) =>
    act(() =>
      root.render(
        <ApplicationContext.Provider
          value={{
            uiTheme,
            darkMode,
            themeMode: darkMode ? "dark" : "light",
            offeredUiThemes: [],
            isSidebarCollapsed: false,
            setUiTheme: () => {},
            setThemeMode: () => {},
            toggleSidebar: () => {},
          }}
        >
          <Probe />
        </ApplicationContext.Provider>,
      ),
    );
  try {
    render("paris", false);
    expect(document.title).toBe("Paris Aéroport");
    expect(favicon.getAttribute("href")).toBe("/images/paris-light.svg");
    render("paris", true);
    expect(favicon.getAttribute("href")).toBe("/images/paris-dark.svg");
    render("pebble", true);
    expect(document.title).toBe("Fred");
    expect(favicon.getAttribute("href")).toBe("/images/fred-dark.svg");
    render("pebble", false);
    expect(favicon.getAttribute("href")).toBe("/images/fred.svg");
    render("single", true);
    expect(document.title).toBe("Fred");
    expect(favicon.getAttribute("href")).toBe("/images/single-icon.svg");
  } finally {
    act(() => root.unmount());
    favicon.remove();
  }
});
