// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const h = vi.hoisted(() => ({
  access: {
    isAdmin: true,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: undefined as unknown,
    currentData: {} as object | undefined,
    refetch: vi.fn(),
  },
  spaces: {
    currentData: [] as object[] | undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: undefined as unknown,
  },
}));
// RTK keeps the last successful `data` when a refetch fails.
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ ...h.spaces, data: h.spaces.currentData }),
}));
vi.mock("@core/hooks/useOrganizationAdmin", () => ({
  useOrganizationAdmin: () => ({ isAdmin: false }),
}));
vi.mock("@core/hooks/useOrganizationSupervisionAccess", () => ({
  useOrganizationSupervisionAccess: () => ({ allowed: false }),
}));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => h.access }));
vi.mock("@shared/layouts/MainLayout/MainLayout", () => ({ default: ({ children }) => <div>{children}</div> }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
import ManagerArea from "./ManagerArea";
import MainNavBar from "@shared/layouts/Sidebar/MainNavBar/MainNavBar";
import AdminNavbar from "@shared/layouts/Sidebar/AdminNavbar/AdminNavbar";
vi.mock("@hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => {
    throw new Error("business bootstrap mounted in platform area");
  },
}));

let host: HTMLDivElement;
let root: Root;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
beforeEach(() => {
  Object.assign(h.access, {
    isAdmin: true,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: undefined,
    currentData: {},
  });
  Object.assign(h.spaces, { currentData: [], isLoading: false, isFetching: false, isError: false, error: undefined });
  vi.clearAllMocks();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
function Draft() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>draft {count}</button>;
}
function render(path = "/home") {
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[path]}>
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
            <Route path="/home" element={<Draft />} />
            <Route path="/team/:id/agents" element={<p>Agents</p>} />
            <Route
              path="/admin/organizations"
              element={
                <>
                  <p>Organizations</p>
                  <Draft />
                </>
              }
            />
            <Route path="/admin/provisioning" element={<p>Provisioning</p>} />
            <Route path="/settings" element={<p>Profile</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    ),
  );
}
const member = () => {
  h.spaces.currentData = [{ id: "org-1", kind: "organization", name: "Acme", roles: ["admin"] }];
};
it.each(["/home", "/team/existing-membership/agents"])(
  "keeps a platform owner without an organization in the platform area from %s",
  (path) => {
    render(path);
    expect(host.textContent).toContain("Organizations");
    expect(host.querySelector("[data-business]")).toBeNull();
  },
);
it.each(["/home", "/team/existing-membership/agents", "/settings"])(
  "opens a member platform owner's own page %s without bouncing to the platform area",
  (path) => {
    member();
    render(path);
    expect(host.textContent).not.toContain("Organizations");
    expect(host.querySelector("[data-business]")).not.toBeNull();
  },
);
it("keeps platform pages out of the business area for a member platform owner", () => {
  member();
  render("/admin/organizations");
  expect(host.textContent).toContain("Organizations");
  expect(host.querySelector("[data-business]")).toBeNull();
});
it("waits for the membership before deciding a platform owner's area", () => {
  h.spaces.isLoading = true;
  h.spaces.currentData = undefined;
  render("/home");
  expect(host.querySelector('[role="status"]')).not.toBeNull();
  expect(host.textContent).not.toContain("Organizations");
});
it("keeps a member platform owner on their page when a membership refetch fails", () => {
  member();
  render("/home");
  h.spaces.isError = true;
  h.spaces.error = { status: 503 };
  render("/home");
  expect(host.textContent).not.toContain("Organizations");
  expect(host.querySelector("[data-business]")).not.toBeNull();
});
it("keeps a platform owner in the platform area when the membership cannot be read", () => {
  h.spaces.isError = true;
  h.spaces.currentData = undefined;
  render("/home");
  expect(host.textContent).toContain("Organizations");
});
it.each(["/settings", "/admin/provisioning"])("retains shared and provisioning destinations: %s", (path) => {
  render(path);
  expect(host.textContent).not.toContain("Organizations");
  expect(host.querySelector("[data-business]")).toBeNull();
});
it.each([true, false])("keeps local page state during authority refresh (owner=%s)", (owner) => {
  h.access.isAdmin = owner;
  render();
  act(() => host.querySelector("button")!.click());
  expect(host.textContent).toContain("draft 1");
  h.access.isFetching = true;
  render();
  expect(host.textContent).toContain("draft 1");
  h.access.isFetching = false;
  render();
  expect(host.textContent).toContain("draft 1");
  expect(!!host.querySelector("[data-business]")).toBe(!owner);
});
it("fails closed on authority error and retries without business fallback", () => {
  render();
  h.access.isError = true;
  render();
  expect(host.textContent).not.toContain("Organizations");
  expect(host.querySelector("[data-business]")).toBeNull();
  act(() => host.querySelector("button")!.click());
  expect(h.access.refetch).toHaveBeenCalledOnce();
});
it("does not mount platform business navigation or its bootstrap hooks", () => {
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/admin/organizations"]}>
        <MainNavBar platformOnly />
        <AdminNavbar platformArea />
      </MemoryRouter>,
    ),
  );
  expect([...host.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
    "/admin/organizations",
    "/admin/provisioning",
  ]);
  expect(host.textContent).not.toContain("rework.mainNav.home");
});

it("keeps a failed authority check blocked while retry is pending with cached data", () => {
  h.access.isAdmin = false;
  render();
  expect(host.querySelector("[data-business]")).not.toBeNull();
  h.access.isError = true;
  h.access.error = { status: 503 };
  render();
  expect(host.querySelector("[data-business]")).toBeNull();
  h.access.isError = false;
  h.access.isFetching = true;
  render();
  expect(host.querySelector("[data-business]")).toBeNull();
  h.access.error = undefined;
  h.access.isFetching = false;
  render();
  expect(host.querySelector("[data-business]")).not.toBeNull();
});
