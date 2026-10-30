// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";

const ORG = [{ id: "org-1", kind: "organization", name: "Acme", roles: ["owner"] }];
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-redux", () => ({ useSelector: () => 0 }));
vi.mock("../../../common/config", () => ({ getConfig: () => ({ platform_access_enabled: false }) }));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ data: ORG, currentData: ORG, isLoading: false, isFetching: false, isError: false }),
}));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({
    isAdmin: true,
    isLoading: false,
    isFetching: false,
    isError: false,
    currentData: {},
    refetch: vi.fn(),
  }),
}));
vi.mock("@core/hooks/useOrganizationOwner", () => ({
  useOrganizationOwner: () => ({ isOwner: true, organizationId: "org-1", currentData: ORG }),
}));
vi.mock("@core/hooks/useOrganizationSupervisionAccess", () => ({
  useOrganizationSupervisionAccess: () => ({ allowed: true }),
}));
vi.mock("@hooks/useUserCapabilities.ts", () => ({ useUserCapabilities: () => ({ canAdmin: true }) }));
vi.mock("@shared/molecules/UserProfile/UserProfile.tsx", () => ({ default: () => null }));
vi.mock("@shared/layouts/Sidebar/MainNavBar/MainNavBar.tsx", () => ({ default: () => null }));
vi.mock("@shared/organisms/TeamAdminCharterGate/TeamAdminCharterGate", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("../../features/tasks/useTaskPolling", () => ({ useTaskPolling: () => undefined }));
vi.mock("../../features/tasks/useTaskRehydration", () => ({ useTaskRehydration: () => undefined }));

import ManagerArea from "./ManagerArea";
import MainLayout from "@shared/layouts/MainLayout/MainLayout";

// The router wraps every route in the same content block, as here.
it("keeps the shell mounted and focus on the switcher when switching from an organization page", () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/admin/teams"]}>
        <Routes>
          <Route
            element={
              <ManagerArea>
                {(business) => (
                  <div data-business={business || undefined}>
                    <Outlet />
                  </div>
                )}
              </ManagerArea>
            }
          >
            <Route path="/" element={<MainLayout />}>
              <Route path="admin/teams" element={<p>Teams page</p>} />
              <Route path="admin/organizations" element={<p>Organizations page</p>} />
            </Route>
          </Route>
        </Routes>
      </MemoryRouter>,
    ),
  );
  expect(host.textContent).toContain("Teams page");
  const trigger = host.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')!;
  act(() => trigger.click());
  act(() => host.querySelector<HTMLButtonElement>('[role="menuitemradio"]')!.click());
  expect(host.textContent).toContain("Organizations page");
  expect(host.querySelector('button[aria-haspopup="menu"]')).toBe(trigger);
  expect(document.activeElement).toBe(trigger);
  act(() => root.unmount());
  host.remove();
});
