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
}));
vi.mock("@core/hooks/useOrganizationAdmin", () => ({
  useOrganizationAdmin: () => ({ isAdmin: false }),
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
                <div data-business>
                  <Outlet />
                </div>
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
it.each(["/home", "/team/existing-membership/agents"])(
  "keeps a mixed-role owner in the platform area from %s",
  (path) => {
    render(path);
    expect(host.textContent).toContain("Organizations");
    expect(host.querySelector("[data-business]")).toBeNull();
  },
);
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
        <MainNavBar platformArea />
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
