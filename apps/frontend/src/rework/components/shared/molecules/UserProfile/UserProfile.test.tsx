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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const identity = vi.hoisted(() => ({ name: "Alice" as string | null, username: "alice" as string | null }));
vi.mock("../../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: {
    GetUserFullName: () => identity.name,
    GetUserName: () => identity.username,
    GetUserId: () => "subject-1",
    GetUserMail: () => "alice@example.com",
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({ useFrontendProperties: () => ({}) }));
vi.mock("../../../../../hooks/useFrontendBootstrap.ts", () => ({ useFrontendBootstrap: () => ({ bootstrap: null }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

import UserProfile from "./UserProfile";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<UserProfile />));
  act(() => container!.querySelector<HTMLButtonElement>("button[aria-haspopup]")!.click());
}

afterEach(() => {
  identity.name = "Alice";
  identity.username = "alice";
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
});

describe("UserProfile", () => {
  it("exposes identity/logout without a bootstrap query or unimplemented destinations", () => {
    mount();
    expect(container!.textContent).toContain("Alice");
    expect(container!.textContent).toContain("alice@example.com");
    expect(container!.textContent).toContain("rework.userSettings.disconnect");
    expect(container!.textContent).not.toContain("rework.profileMenu.profile");
    expect(container!.textContent).not.toContain("rework.profileMenu.whatsNew");
  });
});

it.each(["alice", null])("identifies a person without a name claim using username %s or subject", (username) => {
  identity.name = null;
  identity.username = username;
  mount();
  expect(container!.querySelector('[role="menu"]')?.textContent).toContain(username ?? "subject-1");
});
it("focuses logout when opening and restores the trigger on Escape", () => {
  mount();
  expect(document.activeElement).toBe(container!.querySelector('[role="menuitem"]'));
  act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(container!.querySelector('[role="menu"]')).toBeNull();
  expect(document.activeElement).toBe(container!.querySelector('button[aria-haspopup="menu"]'));
});
