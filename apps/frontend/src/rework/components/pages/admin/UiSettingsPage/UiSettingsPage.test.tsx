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
// page blocks both before the round-trip, and keeps ids it does not ship.

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

// A native select: what is under test is the page's logic, not the dropdown.
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    value,
    onChange,
  }: {
    options: { value: string; label: string }[];
    value: string;
    onChange: (v: string) => void;
  }) => (
    <select data-testid="default-theme" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import UiSettingsPage from "./UiSettingsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

const checkbox = (label: string) =>
  Array.from(container.querySelectorAll("label"))
    .find((l) => l.textContent?.includes(label))!
    .querySelector("input") as HTMLInputElement;
const saveButton = () =>
  Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("rework.uiSettings.save"))!;
const alertText = () => container.querySelector('[role="alert"]')?.textContent ?? null;

function render() {
  act(() => root.render(<UiSettingsPage />));
}

function chooseDefault(value: string) {
  const select = container.querySelector('[data-testid="default-theme"]') as HTMLSelectElement;
  act(() => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

beforeEach(() => {
  h.settings.data = { default_theme: "cobalt", hidden_themes: [], updated_by: null, updated_at: null };
  h.settings.isError = false;
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
  it("shows the stored settings and keeps Save disabled until something changes", () => {
    render();
    expect((container.querySelector('[data-testid="default-theme"]') as HTMLSelectElement).value).toBe("cobalt");
    expect(checkbox("themeCloud").checked).toBe(true);
    expect(saveButton().disabled).toBe(true);
  });

  it("blocks saving when the default theme is hidden", () => {
    render();
    act(() => checkbox("themeCobalt").click());
    expect(alertText()).toBe("rework.uiSettings.errors.defaultHidden");
    expect(saveButton().disabled).toBe(true);
  });

  it("blocks saving when no theme is offered", () => {
    render();
    chooseDefault("");
    act(() => {
      checkbox("themePebble").click();
      checkbox("themeCobalt").click();
      checkbox("themeCloud").click();
    });
    expect(alertText()).toBe("rework.uiSettings.errors.noneOffered");
    expect(saveButton().disabled).toBe(true);
  });

  it("saves the default and the hidden themes, null for no default", async () => {
    render();
    chooseDefault("");
    act(() => checkbox("themePebble").click());
    await act(async () => saveButton().click());
    expect(h.save).toHaveBeenCalledWith({
      setPlatformUiSettingsRequest: { default_theme: null, hidden_themes: ["pebble"] },
    });
  });

  it("says when the settings could not be loaded instead of showing defaults as stored", () => {
    h.settings.isError = true;
    render();
    expect(alertText()).toBe("rework.uiSettings.loadFailed");
    expect(checkbox("themeCloud").closest("fieldset")!.disabled).toBe(true);
  });

  it("keeps ids this version does not ship", async () => {
    h.settings.data = { default_theme: null, hidden_themes: ["aurora"], updated_by: null, updated_at: null };
    render();
    expect(container.textContent).toContain("rework.uiSettings.unknown");
    act(() => checkbox("themeCloud").click());
    await act(async () => saveButton().click());
    expect(h.save).toHaveBeenCalledWith({
      setPlatformUiSettingsRequest: { default_theme: null, hidden_themes: ["aurora", "cloud"] },
    });
  });
});
