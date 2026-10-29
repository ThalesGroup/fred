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
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const spaces = vi.hoisted(() => ({
  current: [] as { kind: string; name: string; roles: string[]; id: string }[] | undefined,
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
  useOrganizationSupervisionAccess: () => ({ allowed: true }),
}));
vi.mock("@core/hooks/useOrganizationAdmin", () => ({
  useOrganizationAdmin: () => ({ isAdmin: true, organizationId: "org-1", currentData: spaces.current }),
}));

import AdminNavbar from "./AdminNavbar";

afterEach(() => {
  spaces.current = [];
});

const render = (platformArea: boolean) => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  const root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/admin/features"]}>
        <AdminNavbar platformArea={platformArea} />
      </MemoryRouter>,
    ),
  );
  const html = container.innerHTML;
  act(() => root.unmount());
  return html;
};

describe("AdminNavbar", () => {
  it("names the platform area and keeps provisioning there", () => {
    const html = render(true);
    expect(html).toContain("rework.sidebar.admin.platformTitle");
    expect(html).toContain('href="/admin/provisioning"');
  });

  it("names the organization area after the organization, without provisioning", () => {
    spaces.current = [
      { kind: "team", name: "Design", roles: ["admin"], id: "team-1" },
      { kind: "organization", name: "Acme", roles: ["admin"], id: "org-1" },
    ];
    const html = render(false);
    expect(html).toContain("rework.sidebar.admin.organizationTitle:Acme");
    expect(html).toContain('href="/admin/supervision"');
    expect(html).not.toContain('href="/admin/provisioning"');
  });

  it("falls back to a generic organization title before the name is known", () => {
    spaces.current = undefined;
    expect(render(false)).toContain("rework.sidebar.admin.organizationFallbackTitle");
  });
});
