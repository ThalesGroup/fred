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

// The shared profile uses manager authority without mounting the Python avatar path.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider.tsx";
import type { UiTheme } from "../../../../app/uiThemes.ts";
import type { Me, MySpace } from "../../../../slices/fredManager/fredManagerOpenApi.ts";

const state = vi.hoisted(() => ({
  spaces: [] as MySpace[],
  spacesError: false,
  spacesFetching: false,
  spacesRefetch: vi.fn(),
  userId: "ada-id",
  username: "ada",
  fullName: "Ada Lovelace",
  email: "ada@example.com",
  authEnabled: true,
  data: undefined as Me | undefined,
  isLoading: false,
  isFetching: false,
  isError: false,
  refetch: vi.fn(),
  logout: vi.fn(),
  setThemeMode: vi.fn(),
  setUiTheme: vi.fn(),
  changeLanguage: vi.fn(),
}));
vi.mock("../../../../common/config", () => ({
  getConfig: () => ({ user_auth: { enabled: state.authEnabled } }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, args?: { roles?: string; name?: string }) =>
      args?.name ? `${key}: ${args.name}` : args?.roles === undefined ? key : `${key}: ${args.roles}`,
    i18n: { language: "fr", changeLanguage: state.changeLanguage },
  }),
}));
vi.mock("../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: {
    GetUserId: () => state.userId,
    GetUserFullName: () => state.fullName,
    GetUserName: () => state.username,
    GetUserMail: () => state.email,
    // A provider admin role must never become a manager platform role.
    GetUserRoles: () => ["admin"],
    CallLogout: state.logout,
  },
}));
vi.mock("../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ siteTitle: "Fred", siteSubtitle: "" }),
}));
vi.mock("../../../../slices/fredManager/fredManagerApiEnhancements.ts", () => ({
  useMeQuery: () => state,
  useMySpacesQuery: () => ({
    currentData: state.spaces,
    isError: state.spacesError,
    isFetching: state.spacesFetching,
    refetch: state.spacesRefetch,
  }),
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    ariaLabel,
    onChange,
  }: {
    options: { value: string }[];
    ariaLabel: string;
    onChange: (value: string) => void;
  }) => (
    <select aria-label={ariaLabel} onChange={(event) => onChange(event.target.value)}>
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
function render(offeredUiThemes: UiTheme[] = ["cobalt"]) {
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
            setThemeMode: state.setThemeMode,
            setUiTheme: state.setUiTheme,
          }}
        >
          <UserSettingsPage />
        </ApplicationContext.Provider>
      </MemoryRouter>,
    ),
  );
}
const themePicker = () =>
  container.querySelector<HTMLSelectElement>('select[aria-label="rework.userSettings.app.uiThemeAria"]');
const clickText = (text: string) =>
  act(() => {
    const button = [...container.querySelectorAll("button")].find((node) => node.textContent?.includes(text));
    expect(button).toBeDefined();
    button!.click();
  });
beforeEach(() => {
  vi.clearAllMocks();
  state.userId = "ada-id";
  state.username = "ada";
  state.fullName = "Ada Lovelace";
  state.email = "ada@example.com";
  state.authEnabled = true;
  state.spaces = [];
  state.spacesError = state.spacesFetching = false;
  state.data = { user_id: "ada-id", username: "ada", platform_roles: ["platform_owner"] };
  state.isLoading = state.isFetching = state.isError = false;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("shared UserSettingsPage", () => {
  it("shows the owner's identity and manager roles with no spaces or photo dependency", () => {
    render();
    expect(container.textContent).toContain("Ada Lovelace");
    expect(container.textContent).toContain("ada@example.com");
    expect(container.textContent).toContain("rework.userSettings.platformRoles: platform_owner");
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(container.textContent).not.toContain("rework.userSettings.picture");
    expect([...container.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "/gdpr",
      "/gcu",
      "/release-notes",
    ]);
    clickText("rework.userSettings.disconnect");
    expect(state.logout).toHaveBeenCalledOnce();
  });
  it("shows an ordinary member's empty platform roles without falling back to provider admin", () => {
    state.data!.platform_roles = [];
    render();
    expect(container.textContent).toContain("rework.userSettings.platformRoles: rework.userSettings.noPlatformRoles");
    expect(container.textContent).not.toContain("platform_owner");
    expect(container.textContent).not.toContain("rework.userSettings.roleAdmin");
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
  it.each(["isLoading", "isFetching"] as const)(
    "distinguishes %s from empty roles and hides stale authority",
    (flag) => {
      state[flag] = true;
      render();
      expect(container.querySelector('[role="status"]')?.textContent).toBe("common.loading");
      expect(container.textContent).not.toContain("platform_owner");
      expect(container.textContent).not.toContain("rework.userSettings.noPlatformRoles");
    },
  );
  it("hides retained roles on failure and offers an explicit retry", () => {
    state.isError = true;
    render();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("rework.manager.unavailable");
    expect(container.textContent).not.toContain("platform_owner");
    clickText("rework.provisioning.retryAuthority");
    expect(state.refetch).toHaveBeenCalledOnce();
  });
  it("never displays the previous subject's roles when accounts switch", () => {
    render();
    state.userId = "bob-id";
    state.username = "bob";
    state.fullName = "Bob Rigg";
    state.email = "bob@app.com";
    render();
    expect(container.textContent).toContain("Bob Rigg");
    expect(container.textContent).toContain("bob@app.com");
    expect(container.textContent).not.toContain("Ada Lovelace");
    expect(container.textContent).not.toContain("ada@example.com");
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.textContent).not.toContain("platform_owner");
    state.data = { user_id: "bob-id", username: "bob", platform_roles: [] };
    render();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.textContent).toContain("rework.userSettings.noPlatformRoles");
  });
  it("refreshes authority on focus and removes the listener on exit", () => {
    render();
    act(() => window.dispatchEvent(new Event("focus")));
    expect(state.refetch).toHaveBeenCalledOnce();
    act(() => root.render(null));
    act(() => window.dispatchEvent(new Event("focus")));
    expect(state.refetch).toHaveBeenCalledOnce();
  });
  it("uses the manager mock subject in unauthenticated development mode", () => {
    state.authEnabled = false;
    state.userId = "dev";
    state.data = { user_id: "admin", username: "admin", platform_roles: ["platform_owner"] };
    render();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.textContent).toContain("rework.userSettings.platformRoles: platform_owner");
  });
  it("retains the offered themes and existing mode/language preference handlers", () => {
    render(["cobalt", "cloud"]);
    expect([...themePicker()!.options].map((o) => o.value)).toEqual(["cobalt", "cloud"]);
    act(() => {
      themePicker()!.value = "cloud";
      themePicker()!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(state.setUiTheme).toHaveBeenCalledWith("cloud");
    clickText("rework.userSettings.app.dark");
    expect(state.setThemeMode).toHaveBeenCalledWith("dark");
    clickText("rework.userSettings.app.english");
    expect(state.changeLanguage).toHaveBeenCalledWith("en");
  });
  it("hides a single offered theme but keeps the mode choice", () => {
    render();
    expect(themePicker()).toBeNull();
    expect(container.querySelector('[aria-label="rework.userSettings.app.themeAria"]')).not.toBeNull();
  });
});

it("shows organization only from current successful manager memberships", () => {
  state.spaces = [
    {
      id: "org",
      name: "Demo",
      kind: "organization",
      organization_id: "org",
      path: ["org"],
      parent_id: null,
      personal_owner: null,
      roles: ["member"],
      inherited_roles: [],
    },
  ];
  render();
  expect(container.textContent).toContain("rework.userSettings.organization: Demo");
  state.spacesFetching = true;
  render();
  expect(container.textContent).not.toContain("Demo");
  state.spacesFetching = false;
  state.spacesError = true;
  render();
  expect(container.textContent).not.toContain("Demo");
  clickText("rework.provisioning.retryAuthority");
  expect(state.spacesRefetch).toHaveBeenCalledOnce();
  state.spacesError = false;
  state.userId = "different-person";
  render();
  expect(container.textContent).not.toContain("Demo");
});
