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
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  spaces: [] as { kind: string; name: string; roles: string[]; id: string }[] | undefined,
  platformOwner: true,
  organizationOwner: true,
  supervision: true,
  selectOrganization: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) => (options?.name ? `${key}:${options.name}` : key),
  }),
}));
vi.mock("react-redux", () => ({ useSelector: () => 0 }));
vi.mock("../../../../../../common/config", () => ({ getConfig: () => ({ platform_access_enabled: false }) }));
vi.mock("@hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => ({ canAdmin: true, canManageTeams: true, canManagePlatformAccess: true }),
}));
vi.mock("@core/hooks/useOrganizationSupervisionAccess", () => ({
  useOrganizationSupervisionAccess: () => {
    const organizations =
      h.spaces?.filter(
        (space) =>
          space.kind === "organization" &&
          (space.roles.includes("owner") || space.roles.includes("organization_admin")),
      ) ?? [];
    return {
      allowed: h.supervision,
      offered: h.supervision,
      organizations,
      organization: organizations[0],
      selectOrganization: h.selectOrganization,
    };
  },
}));
vi.mock("@core/hooks/useOrganizationOwner", () => ({
  useOrganizationOwner: () => ({ isOwner: h.organizationOwner, organizationId: "org-1", currentData: h.spaces }),
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({
    currentData: h.spaces,
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({ isAdmin: h.platformOwner }),
}));

import AdminNavbar from "./AdminNavbar";

const ACME = [
  { kind: "team", name: "Design", roles: ["owner"], id: "team-1" },
  { kind: "organization", name: "Acme", roles: ["owner", "organization_admin"], id: "org-1" },
];
const PLATFORM_PAGES = ["/admin/organizations", "/admin/provisioning", "/admin/monitor", "/admin/self-test"];

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Object.assign(h, { spaces: [], platformOwner: true, organizationOwner: true, supervision: true });
  h.selectOrganization.mockClear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function Where() {
  return <output data-path>{useLocation().pathname}</output>;
}
// The sidebar picks the menu from the route, as MainLayout does.
function Shell() {
  const { pathname } = useLocation();
  return <AdminNavbar platformArea={PLATFORM_PAGES.includes(pathname)} />;
}
const render = (path: string) =>
  act(() =>
    root.render(
      <MemoryRouter key={path} initialEntries={[path]}>
        <Shell />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    ),
  );
const hrefs = () => [...host.querySelectorAll("nav a, a")].map((a) => a.getAttribute("href"));
const path = () => host.querySelector("[data-path]")?.textContent;
const trigger = () => host.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
const items = () => [...host.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')];

describe("AdminNavbar", () => {
  it("offers multiple organizations without platform rights and selects one", () => {
    h.platformOwner = false;
    h.spaces = [...ACME, { kind: "organization", name: "Globex", roles: ["organization_admin"], id: "org-2" }];
    render("/admin/supervision");
    act(() => trigger()!.click());
    expect(items()).toHaveLength(2);
    expect(items()[0].textContent).toContain("Acme");
    expect(items()[1].textContent).toContain("Globex");
    act(() => items()[1].click());
    expect(h.selectOrganization).toHaveBeenCalledWith("org-2");
    expect(path()).toBe("/admin/supervision");
  });

  it("re-enters the guarded landing when changing organization from an Owner page", () => {
    h.spaces = [...ACME, { kind: "organization", name: "Globex", roles: ["organization_admin"], id: "org-2" }];
    render("/admin/features");
    act(() => trigger()!.click());
    act(() => items()[2].click());
    expect(h.selectOrganization).toHaveBeenCalledWith("org-2");
    expect(path()).toBe("/admin");
  });

  it("lists only platform pages in the platform space", () => {
    h.spaces = ACME;
    render("/admin/organizations");
    expect(hrefs()).toEqual(PLATFORM_PAGES);
  });

  it.each(["organization", "team", "project"])("offers self-tests for a platform admin owning a %s", (kind) => {
    h.spaces = [{ kind, name: "Owned space", roles: ["owner"], id: "owned" }];
    h.organizationOwner = false;
    render("/admin/organizations");
    expect(hrefs()).toContain("/admin/self-test");
  });
  it.each([[], ["member"], ["editor"], ["analyst"], ["organization_admin"]].map((roles) => ({ roles })))(
    "hides self-tests without ownership ($roles)",
    ({ roles }) => {
      h.spaces = [{ kind: "organization", name: "Space", roles, id: "space" }];
      render("/admin/organizations");
      expect(hrefs()).not.toContain("/admin/self-test");
    },
  );
  it("excludes personal-space ownership", () => {
    h.spaces = [{ kind: "personal", name: "Personal", roles: ["owner"], id: "personal" }];
    render("/admin/organizations");
    expect(hrefs()).not.toContain("/admin/self-test");
  });
  it("hides self-tests from an owner without platform administration", () => {
    h.platformOwner = false;
    h.spaces = ACME;
    render("/admin/organizations");
    expect(hrefs()).not.toContain("/admin/self-test");
  });

  it("lists only organization pages in the organization space", () => {
    h.spaces = ACME;
    render("/admin/features");
    expect(hrefs()[0]).toBe("/admin/supervision");
    expect(hrefs()).toContain("/admin/features");
    expect(hrefs().filter((href) => PLATFORM_PAGES.includes(href!))).toEqual([]);
  });

  it("names the platform space read-only for a platform admin only", () => {
    render("/admin/organizations");
    expect(trigger()).toBeNull();
    expect(host.querySelector("h2")?.textContent).toBe("rework.sidebar.admin.title");
    expect(host.textContent).toContain("rework.sidebar.admin.platformTitle");
  });

  it("names the organization space without a switcher for an organization admin only", () => {
    h.spaces = ACME;
    h.platformOwner = false;
    render("/admin/features");
    expect(trigger()).toBeNull();
    expect(host.querySelector("h2")?.textContent).toBe("rework.sidebar.admin.title");
    expect(host.textContent).toContain("Acme");
  });

  it("heads the organization panel with the section alone before the name is known", () => {
    h.spaces = undefined;
    h.platformOwner = false;
    render("/admin/features");
    expect(host.querySelector("h2")?.textContent).toBe("rework.sidebar.admin.title");
    expect(host.textContent).not.toContain("rework.sidebar.admin.platformTitle");
  });

  it("shows the switcher on the current space for a person with both spaces", () => {
    h.spaces = ACME;
    render("/admin/organizations");
    expect(trigger()!.textContent).toContain("rework.sidebar.admin.title");
    expect(trigger()!.textContent).toContain("rework.sidebar.admin.platformTitle");
    render("/admin/features");
    expect(trigger()!.textContent).toContain("rework.sidebar.admin.title");
    expect(trigger()!.textContent).toContain("Acme");
    expect(host.querySelector("h2")?.contains(trigger())).toBe(true);
  });

  it("keeps the switcher while the supervision check refetches", () => {
    h.spaces = ACME;
    h.organizationOwner = false;
    h.supervision = false;
    render("/admin/organizations");
    expect(trigger()).not.toBeNull();
  });

  it("shows no switcher to a plain organization member", () => {
    h.spaces = [{ kind: "organization", name: "Acme", roles: ["member"], id: "org-1" }];
    h.organizationOwner = false;
    h.supervision = false;
    render("/admin/organizations");
    expect(trigger()).toBeNull();
  });

  it("labels each group and moves between spaces with the arrow, Home and End keys", () => {
    h.spaces = ACME;
    render("/admin/features");
    act(() => trigger()!.click());
    const groups = [...host.querySelectorAll('[role="menu"] [role="group"]')];
    expect(groups.map((group) => document.getElementById(group.getAttribute("aria-labelledby")!)?.textContent)).toEqual(
      ["rework.sidebar.admin.platformTitle", "rework.sidebar.admin.spaces.organizations"],
    );
    const press = (key: string) =>
      act(() => {
        (document.activeElement as HTMLElement).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      });
    expect(document.activeElement).toBe(items()[1]);
    press("ArrowDown");
    expect(document.activeElement).toBe(items()[0]);
    press("ArrowUp");
    expect(document.activeElement).toBe(items()[1]);
    press("Home");
    expect(document.activeElement).toBe(items()[0]);
    press("End");
    expect(document.activeElement).toBe(items()[1]);
    press("Tab");
    expect(items()).toEqual([]);
  });

  it("lists both spaces, with the roles held in the organization, and focuses the current one", () => {
    h.spaces = ACME;
    render("/admin/features");
    act(() => trigger()!.click());
    expect(items()[0].textContent).toContain("rework.sidebar.admin.spaces.platform");
    expect(items()[1].textContent).toContain(
      "Acmerework.supervision.roleNames.organization_admin, rework.supervision.roleNames.owner",
    );
    expect(items().map((item) => item.getAttribute("aria-checked"))).toEqual(["false", "true"]);
    expect(document.activeElement).toBe(items()[1]);
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(items()).toEqual([]);
    expect(document.activeElement).toBe(trigger());
  });

  it("changes space only from the switcher and gives focus back to it", () => {
    h.spaces = ACME;
    render("/admin/features");
    act(() => trigger()!.click());
    act(() => items()[0].click());
    expect(path()).toBe("/admin/organizations");
    expect(hrefs()).toEqual(PLATFORM_PAGES);
    expect(document.activeElement).toBe(trigger());
    act(() => trigger()!.click());
    act(() => items()[1].click());
    expect(path()).toBe("/admin");
  });

  it("stays put when the current space is picked again", () => {
    h.spaces = ACME;
    render("/admin/organizations");
    act(() => trigger()!.click());
    act(() => items()[0].click());
    expect(path()).toBe("/admin/organizations");
  });
});
