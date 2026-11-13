// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MySpace } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { WorkingOrganizationProvider, useWorkingOrganization } from "./useWorkingOrganization";
import WorkingOrganizationRoute from "../guards/WorkingOrganizationRoute";

const h = vi.hoisted(() => ({
  identity: "boss",
  spaces: [] as MySpace[],
  catalogues: [] as { space_id: string; name: string }[],
  loading: false,
  error: undefined as unknown,
  refetch: vi.fn(),
  t: (key: string, values?: { name?: string }) => (values?.name ? `${key}:${values.name}` : key),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.t }) }));
vi.mock("../../../security/KeycloakService", () => ({ KeyCloakService: { GetSessionIdentity: () => h.identity } }));
vi.mock("../../../slices/controlPlane/controlPlaneApi", () => ({ sessionQueryArgs: (args: unknown) => args }));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({
    currentData: h.spaces,
    isLoading: h.loading,
    isError: !!h.error,
    error: h.error,
    refetch: h.refetch,
  }),
  useMarketplacesQuery: () => ({ currentData: { items: h.catalogues }, isLoading: h.loading, refetch: h.refetch }),
}));

let root: Root;
let host: HTMLDivElement;
let context: ReturnType<typeof useWorkingOrganization>;
const space = (id: string, org = id, kind: MySpace["kind"] = "organization"): MySpace => ({
  id,
  name: id,
  organization_id: org,
  kind,
  roles: ["member"],
  parent_id: null,
  personal_owner: null,
  path: [org, id],
});
function Probe() {
  context = useWorkingOrganization();
  const { pathname } = useLocation();
  return <output data-path={pathname}>{context.organizationId ?? "no-context"}</output>;
}
function render(route = "/home") {
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[route]}>
        <WorkingOrganizationProvider>
          <Probe />
          <WorkingOrganizationRoute silent>
            <p data-nav-resource>navigation resource</p>
          </WorkingOrganizationRoute>
          <WorkingOrganizationRoute>
            <p data-resource>resource</p>
          </WorkingOrganizationRoute>
        </WorkingOrganizationProvider>
      </MemoryRouter>,
    ),
  );
}
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  Object.assign(h, {
    identity: "boss",
    spaces: [space("Acme"), space("Globex")],
    catalogues: [],
    loading: false,
    error: undefined,
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.restoreAllMocks();
});

it("shares one selection, restores it on reload, and does not follow other tabs", () => {
  render();
  expect(context.organizationId).toBe("Acme");
  act(() => {
    context.selectOrganization("Globex");
  });
  expect(host.querySelector("output")?.textContent).toBe("Globex");
  expect(sessionStorage.getItem("working.organization:boss")).toBe("Globex");
  act(() =>
    window.dispatchEvent(
      new StorageEvent("storage", { key: "working.organization:boss", newValue: "Acme", storageArea: localStorage }),
    ),
  );
  expect(context.organizationId).toBe("Globex");
  act(() => root.render(null));
  render();
  expect(context.organizationId).toBe("Globex");
});

it("never falls back to another organization after revocation or a transient failure", () => {
  render();
  act(() => {
    context.selectOrganization("Globex");
  });
  h.error = { status: 503 };
  render();
  expect(context.organizationId).toBeUndefined();
  expect(host.querySelector("[data-resource]")).toBeNull();
  expect(host.querySelector("[data-nav-resource]")).toBeNull();
  expect(sessionStorage.getItem("working.organization:boss")).toBe("Globex");
  h.error = undefined;
  h.spaces = [space("Acme")];
  render();
  expect(context.organizationId).toBeUndefined();
  act(() => {
    expect(context.selectOrganization("unauthorized")).toBe(false);
  });
  act(() => {
    context.selectOrganization("Acme");
  });
  expect(context.organizationId).toBe("Acme");
});

it("includes direct project and catalogue participation without inventing organization roles", () => {
  h.spaces = [space("Support", "Globex", "project")];
  h.catalogues = [{ space_id: "Globex", name: "Globex" }];
  render();
  expect(context.organizations).toEqual([{ id: "Globex", name: "Globex" }]);
  expect(context.memberships.currentData).toEqual(h.spaces);
});

it("does not leak the previous identity or expose a context during initial loading", () => {
  render();
  act(() => {
    context.selectOrganization("Globex");
  });
  h.identity = "alice";
  h.loading = true;
  h.spaces = [];
  render();
  expect(context.organizationId).toBeUndefined();
  expect(host.querySelector("[data-resource]")).toBeNull();
  expect(host.querySelector("[data-nav-resource]")).toBeNull();
  h.loading = false;
  h.spaces = [space("Acme")];
  render();
  expect(context.organizationId).toBe("Acme");
});

it.each(["/team/Globex/agents", "/marketplace/prompts?catalogue=Globex&entry=entry-1"])(
  "requires an explicit context change before opening %s",
  (route) => {
    sessionStorage.setItem("working.organization:boss", "Acme");
    render(route);
    expect(host.querySelector("[data-resource]")).toBeNull();
    expect(host.querySelector("[data-nav-resource]")).toBeNull();
    expect(host.textContent).toContain("rework.profileMenu.organizationLink:Globex");
    act(() => host.querySelector<HTMLButtonElement>("button")!.click());
    expect(context.organizationId).toBe("Globex");
    expect(host.querySelector("[data-resource]")).not.toBeNull();
    expect(host.querySelector("[data-nav-resource]")).not.toBeNull();
  },
);

it("rejects an unknown catalogue instead of displaying the first available one", () => {
  render("/marketplace/prompts?catalogue=unknown&entry=entry-1");
  expect(context.organizationId).toBe("Acme");
  expect(host.querySelector("[data-resource]")).toBeNull();
  expect(host.querySelector("[data-nav-resource]")).toBeNull();
});

it("blocks an unknown or revoked direct space link before mounting its consumers", () => {
  h.spaces.push(space("globex-team", "Globex", "team"));
  sessionStorage.setItem("working.organization:boss", "Acme");
  render("/team/globex-team/usage");
  expect(host.querySelector("[data-resource]")).toBeNull();
  expect(host.querySelector("[data-nav-resource]")).toBeNull();
  act(() => host.querySelector<HTMLButtonElement>("button")!.click());
  expect(context.organizationId).toBe("Globex");
  expect(host.querySelector("[data-resource]")).not.toBeNull();
  expect(host.querySelector("[data-nav-resource]")).not.toBeNull();
  h.spaces = h.spaces.filter((space) => space.id !== "globex-team");
  render("/team/globex-team/usage");
  expect(context.organizationId).toBe("Globex");
  expect(host.querySelector("[data-resource]")).toBeNull();
  expect(host.querySelector("[data-nav-resource]")).toBeNull();
  expect(host.textContent).toContain("rework.manager.unavailable");
});

it("keeps two mounted tab contexts independent, including their restored choices", () => {
  // Two stores represent the browser-owned sessionStorage partition per tab.
  const tabA = new Map<string, string>();
  const tabB = new Map<string, string>();
  let activeStorage = tabA;
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => activeStorage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      activeStorage.set(key, value);
    },
  });
  render();
  const first = context;
  const secondHost = document.createElement("div");
  const secondRoot = createRoot(secondHost);
  let second: ReturnType<typeof useWorkingOrganization>;
  function OtherTab() {
    second = useWorkingOrganization();
    return <output>{second.organizationId ?? "no-context"}</output>;
  }
  const mountSecond = () =>
    act(() =>
      secondRoot.render(
        <WorkingOrganizationProvider>
          <OtherTab />
        </WorkingOrganizationProvider>,
      ),
    );
  try {
    activeStorage = tabB;
    mountSecond();
    act(() => {
      second.selectOrganization("Globex");
    });
    expect(secondHost.textContent).toBe("Globex");
    expect(host.querySelector("output")?.textContent).toBe("Acme");
    activeStorage = tabA;
    act(() => {
      first.selectOrganization("Globex");
    });
    expect(host.querySelector("output")?.textContent).toBe("Globex");
    activeStorage = tabB;
    act(() => {
      second.selectOrganization("Acme");
    });
    expect(secondHost.textContent).toBe("Acme");
    expect(host.querySelector("output")?.textContent).toBe("Globex");
    act(() => secondRoot.render(null));
    mountSecond();
    expect(secondHost.textContent).toBe("Acme");
    activeStorage = tabA;
    act(() => root.render(null));
    render();
    expect(host.querySelector("output")?.textContent).toBe("Globex");
    expect(tabA.get("working.organization:boss")).toBe("Globex");
    expect(tabB.get("working.organization:boss")).toBe("Acme");
  } finally {
    act(() => secondRoot.unmount());
    vi.unstubAllGlobals();
  }
});

it("resolves the personal alias only inside the selected organization", () => {
  const acmePersonal = "2fefb32a-910f-4d88-8df4-3605ec3edcc0";
  const globexPersonal = "293d5ce1-a604-4e45-b285-db9397ff1668";
  h.spaces.push(space(acmePersonal, "Acme", "personal"), space(globexPersonal, "Globex", "personal"));
  sessionStorage.setItem("working.organization:boss", "Globex");
  render("/team/personal/usage");
  expect(context.organizationId).toBe("Globex");
  expect(host.querySelector("output")?.getAttribute("data-path")).toBe(`/team/${globexPersonal}/usage`);
  expect(host.querySelector("[data-resource]")).not.toBeNull();
  expect(host.querySelector("[data-nav-resource]")).not.toBeNull();
});
