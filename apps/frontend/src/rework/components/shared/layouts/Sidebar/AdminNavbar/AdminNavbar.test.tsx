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

vi.mock("@core/hooks/useWorkingOrganization", () => ({
  useWorkingOrganization: () => ({ organization: h.spaces?.find((space) => space.kind === "organization") }),
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

describe("AdminNavbar", () => {
  it("shows the working organization read-only, even with access to several organizations", () => {
    h.platformOwner = false;
    h.spaces = [...ACME, { kind: "organization", name: "Globex", roles: ["owner"], id: "org-2" }];
    render("/admin/features");
    expect(host.textContent).toContain("Acme");
    expect(host.textContent).not.toContain("Globex");
    expect(trigger()).toBeNull();
    expect(hrefs()).toContain("/admin/supervision");
    expect(hrefs()).toContain("/admin/features");
    expect(hrefs()).not.toContain("/admin/organizations");
  });

  it("keeps a link between platform administration and the active organization's administration", () => {
    h.spaces = ACME;
    render("/admin/features");
    act(() => host.querySelector<HTMLAnchorElement>('a[href="/admin/organizations"]')!.click());
    expect(path()).toBe("/admin/organizations");
    expect(hrefs()).toEqual(["/admin", ...PLATFORM_PAGES]);
    expect(trigger()).toBeNull();
    act(() => host.querySelector<HTMLAnchorElement>('a[href="/admin"]')!.click());
    expect(path()).toBe("/admin");
  });

  it("does not offer organization administration to a platform-only user", () => {
    h.organizationOwner = false;
    h.supervision = false;
    render("/admin/organizations");
    expect(hrefs()).not.toContain("/admin");
    expect(host.textContent).toContain("rework.sidebar.admin.platformTitle");
    expect(trigger()).toBeNull();
  });

  it.each(["organization", "team", "project"])("offers self-tests to a platform admin owning a %s", (kind) => {
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

  it("excludes personal-space ownership from self-tests", () => {
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
});
