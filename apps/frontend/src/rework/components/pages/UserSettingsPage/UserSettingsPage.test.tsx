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

// The theme picker lists only the themes the platform offers, and disappears
// when there is nothing to choose; the light/dark/system choice always stays.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider.tsx";
import type { UiTheme } from "../../../../app/uiThemes.ts";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr", changeLanguage: vi.fn() } }),
}));

vi.mock("../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: {
    GetUserFullName: () => "Ada Lovelace",
    GetUserName: () => "ada",
    GetUserMail: () => "ada@example.com",
    GetUserRoles: () => [],
    CallLogout: vi.fn(),
  },
}));

vi.mock("../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ siteTitle: "Fred", siteSubtitle: "" }),
}));

vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({ options, ariaLabel }: { options: { value: string }[]; ariaLabel: string }) => (
    <select aria-label={ariaLabel}>
      {options.map((o) => (
        <option key={o.value} value={o.value} />
      ))}
    </select>
  ),
}));

import UserSettingsPage from "./UserSettingsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render(offeredUiThemes: UiTheme[]) {
  act(() =>
    root.render(
      <MemoryRouter>
        <ApplicationContext.Provider
          value={{
            isSidebarCollapsed: false,
            darkMode: false,
            themeMode: "system",
            uiTheme: offeredUiThemes[0],
            offeredUiThemes,
            toggleSidebar: () => undefined,
            setThemeMode: () => undefined,
            setUiTheme: () => undefined,
          }}
        >
          <UserSettingsPage />
        </ApplicationContext.Provider>
      </MemoryRouter>,
    ),
  );
}

const themePicker = () => container.querySelector('select[aria-label="rework.userSettings.app.uiThemeAria"]');
const modeGroup = () => container.querySelector('[aria-label="rework.userSettings.app.themeAria"]');

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("UserSettingsPage theme picker", () => {
  it("lists only the offered themes", () => {
    render(["cobalt", "cloud"]);
    const values = Array.from(themePicker()!.querySelectorAll("option")).map((o) => o.getAttribute("value"));
    expect(values).toEqual(["cobalt", "cloud"]);
  });

  it("hides the picker when a single theme is offered but keeps the mode choice", () => {
    render(["cobalt"]);
    expect(themePicker()).toBeNull();
    expect(modeGroup()).not.toBeNull();
  });
});
