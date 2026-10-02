// @vitest-environment happy-dom
// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Saving must never leave users with no theme or with a hidden default: the
// tiles make both impossible, and the page keeps ids it does not ship.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  settings: {
    data: {
      default_theme: "cobalt" as string | null,
      hidden_themes: [] as string[],
      updated_by: null,
      updated_at: null,
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  },
  save: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformUiSettingsQuery: () => h.settings,
  useSetPlatformUiSettingsMutation: () => [h.save, { isLoading: false }],
  useUsersByIdsQuery: () => ({ data: [] }),
}));

import UiSettingsPage from "./UiSettingsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

// Each tile is an <li> holding the theme label key.
const tile = (label: string) =>
  Array.from(container.querySelectorAll("li")).find((li) => li.textContent?.includes(label))!;
const offeredSwitch = (label: string) => tile(label).querySelector('input[type="checkbox"]') as HTMLInputElement;
const defaultButton = (label: string) => tile(label).querySelector("button") as HTMLButtonElement;
const alertText = () => container.querySelector('[role="alert"]')?.textContent ?? null;

function render() {
  act(() => root.render(<UiSettingsPage />));
}

beforeEach(() => {
  h.settings.data = { default_theme: "cobalt", hidden_themes: [], updated_by: null, updated_at: null };
  h.settings.isError = false;
  h.settings.isFetching = false;
  h.save.mockReset();
  h.save.mockReturnValue({ unwrap: () => Promise.resolve({}) });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("UiSettingsPage", () => {
  it("shows the stored settings without saving anything", () => {
    render();
    expect(defaultButton("themeCobalt").textContent).toContain("rework.uiSettings.isDefault");
    expect(defaultButton("themePebble").textContent).toContain("rework.uiSettings.setDefault");
    expect(offeredSwitch("themeCloud").checked).toBe(true);
    const previews = Array.from(tile("themeCloud").querySelectorAll('[data-ui-theme="cloud"][data-theme]'));
    expect(previews.map((el) => el.getAttribute("data-theme"))).toEqual(["light", "dark"]);
    expect(h.save).not.toHaveBeenCalled();
  });

  it("shows Pebble as the default when nothing was saved", () => {
    h.settings.data = { default_theme: null, hidden_themes: [], updated_by: null, updated_at: null };
    render();
    expect(defaultButton("themePebble").disabled).toBe(true);
    expect(defaultButton("themePebble").textContent).toContain("rework.uiSettings.isDefault");
  });

  it("saves as soon as a theme is withdrawn or set as default", async () => {
    render();
    await act(async () => offeredSwitch("themePebble").click());
    expect(h.save).toHaveBeenLastCalledWith({
      setPlatformUiSettingsRequest: { default_theme: "cobalt", hidden_themes: ["pebble"] },
    });
    await act(async () => defaultButton("themeCloud").click());
    expect(h.save).toHaveBeenLastCalledWith({
      setPlatformUiSettingsRequest: { default_theme: "cloud", hidden_themes: ["pebble"] },
    });
  });

  it("goes back to the stored settings when a save fails", async () => {
    h.save.mockReturnValue({ unwrap: () => Promise.reject({ status: 422, data: { detail: "nope" } }) });
    render();
    await act(async () => offeredSwitch("themeCloud").click());
    expect(offeredSwitch("themeCloud").checked).toBe(true);
    expect(alertText()).not.toBeNull();
  });

  it("never lets the default theme be withdrawn, nor a withdrawn theme become the default", async () => {
    render();
    expect(offeredSwitch("themeCobalt").disabled).toBe(true);
    await act(async () => offeredSwitch("themeCloud").click());
    expect(offeredSwitch("themeCloud").checked).toBe(false);
    expect(defaultButton("themeCloud").disabled).toBe(true);
  });

  it("keeps the last offered theme offered", async () => {
    h.settings.data = { default_theme: "aurora", hidden_themes: [], updated_by: null, updated_at: null };
    render();
    await act(async () => offeredSwitch("themePebble").click());
    await act(async () => offeredSwitch("themeCobalt").click());
    expect(offeredSwitch("themeCloud").disabled).toBe(true);
  });

  it("locks the tiles while the settings are refetched after a save", () => {
    h.settings.isFetching = true;
    render();
    expect(offeredSwitch("themeCloud").disabled).toBe(true);
    expect(defaultButton("themeCloud").disabled).toBe(true);
  });

  it("says when the settings could not be loaded instead of showing defaults as stored", () => {
    h.settings.isError = true;
    render();
    expect(alertText()).toBe("rework.uiSettings.loadFailed");
    expect(offeredSwitch("themeCloud").disabled).toBe(true);
    expect(defaultButton("themeCloud").disabled).toBe(true);
  });

  it("shows every theme offered when all of them were stored as hidden, and saves a valid state", async () => {
    h.settings.data = {
      default_theme: null,
      hidden_themes: ["pebble", "cobalt", "cloud", "aurora"],
      updated_by: null,
      updated_at: null,
    };
    render();
    expect(offeredSwitch("themeCobalt").checked).toBe(true);
    expect(defaultButton("themePebble").textContent).toContain("rework.uiSettings.isDefault");
    await act(async () => offeredSwitch("themeCloud").click());
    expect(h.save).toHaveBeenCalledWith({
      setPlatformUiSettingsRequest: { default_theme: "pebble", hidden_themes: ["aurora", "cloud"] },
    });
  });

  it("keeps ids this version does not ship", async () => {
    h.settings.data = { default_theme: null, hidden_themes: ["aurora"], updated_by: null, updated_at: null };
    render();
    expect(container.textContent).toContain("rework.uiSettings.unknown");
    await act(async () => offeredSwitch("themeCloud").click());
    expect(h.save).toHaveBeenCalledWith({
      setPlatformUiSettingsRequest: { default_theme: "pebble", hidden_themes: ["aurora", "cloud"] },
    });
  });
});
