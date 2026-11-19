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
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ supervision: false, platformAdmin: false, owner: false, navigate: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => h.navigate, useLocation: () => ({ pathname: "/home" }) }));
vi.mock("@core/hooks/useOrganizationSupervisionAccess", () => ({
  useOrganizationSupervisionAccess: () => ({ offered: h.supervision }),
}));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({ isAdmin: h.platformAdmin }),
}));
vi.mock("@core/hooks/useOrganizationOwner", () => ({ useOrganizationOwner: () => ({ isOwner: h.owner }) }));
vi.mock("@hooks/useUserCapabilities.ts", () => ({ useUserCapabilities: () => ({ canAdmin: false }) }));

import { AdminConsoleMenuItem } from "./AdminConsoleMenuItem";

const render = (onClose = vi.fn()) => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  act(() => createRoot(container).render(<AdminConsoleMenuItem onClose={onClose} />));
  return container;
};

it("stays hidden without any admin-tier role", () => {
  expect(render().textContent).toBe("");
});

it.each(["supervision", "platformAdmin", "owner"] as const)("opens the console for a %s role", (role) => {
  h.supervision = h.platformAdmin = h.owner = false;
  h[role] = true;
  const onClose = vi.fn();
  const item = render(onClose).querySelector("button")!;
  expect(item.textContent).toContain("rework.mainNav.adminConsole");
  act(() => item.click());
  expect(onClose).toHaveBeenCalled();
  expect(h.navigate).toHaveBeenCalledWith("/admin");
});
