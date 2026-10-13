// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({
  givenName: "Camille" as string | null,
  fullName: "Camille Durand" as string | null,
  email: "camille.durand@example.org" as string | null,
  support: "https://support.example.org",
  basename: "/" as string,
  logout: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => (values ? `${key} ${Object.values(values).join(" ")}` : key),
  }),
}));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ contactSupportLink: state.support, siteDisplayName: "Acme Assistant" }),
}));
vi.mock("../../../../common/config", () => ({ getConfig: () => ({ frontend_basename: state.basename }) }));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetUserGivenName: () => state.givenName,
    GetUserFullName: () => state.fullName,
    GetUserMail: () => state.email,
    CallLogout: state.logout,
  },
}));
import PlatformAccessDeniedPage from "./PlatformAccessDeniedPage";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
const open = vi.fn();
beforeEach(() => {
  Object.assign(state, {
    givenName: "Camille",
    fullName: "Camille Durand",
    email: "camille.durand@example.org",
    support: "https://support.example.org",
    basename: "/",
  });
  vi.clearAllMocks();
  vi.stubGlobal("open", open);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
const render = () => act(() => root.render(<PlatformAccessDeniedPage />));
const button = (key: string) => [...host.querySelectorAll("button")].find((node) => node.textContent === key);
const steps = () => [...host.querySelectorAll("ol > li")].map((node) => node.textContent);

it("greets the person, shows their account and the two steps", () => {
  render();
  const headings = host.querySelectorAll("h1");
  expect(headings).toHaveLength(1);
  expect(headings[0].textContent).toBe(
    "rework.platformAccess.denied.greetingNamed Camille rework.platformAccess.denied.title",
  );
  expect(host.querySelector("section")?.getAttribute("aria-labelledby")).toBe(headings[0].id);
  expect(host.textContent).toContain("Acme Assistant");
  expect(host.textContent).toContain("Camille Durand");
  expect(host.textContent).toContain("camille.durand@example.org");
  expect(steps()).toEqual([
    "rework.platformAccess.denied.stepRequestWithEmail",
    "rework.platformAccess.denied.stepReturn",
  ]);
  expect(host.querySelector('[role="alert"]')).toBeNull();
});

it("falls back to a greeting without a name", () => {
  state.givenName = null;
  render();
  expect(host.querySelector("h1")?.textContent).toBe(
    "rework.platformAccess.denied.greeting rework.platformAccess.denied.title",
  );
  expect(host.textContent).toContain("Camille Durand");
});

it("does not point at an address when no email is known", () => {
  state.email = null;
  render();
  expect(host.textContent).toContain("Camille Durand");
  expect(steps()[0]).toBe("rework.platformAccess.denied.stepRequest");
});

it("shows the email alone when the name is unknown", () => {
  state.givenName = null;
  state.fullName = null;
  render();
  expect(host.textContent?.match(/camille\.durand@example\.org/g)).toHaveLength(1);
  expect(steps()[0]).toBe("rework.platformAccess.denied.stepRequestWithEmail");
});

it("renders no account block when neither name nor email is known", () => {
  Object.assign(state, { givenName: null, fullName: null, email: null });
  render();
  expect(host.querySelector("ol")?.previousElementSibling).toBeNull();
  expect(steps()).toHaveLength(2);
});

it("opens the support link in a new tab, and offers sign-out and a re-check", () => {
  render();
  act(() => button("rework.platformAccess.denied.request")!.click());
  expect(open).toHaveBeenCalledWith("https://support.example.org", "_blank", "noopener,noreferrer");
  expect(button("rework.platformAccess.denied.check")).toBeDefined();
  act(() => button("rework.platformAccess.signOut")!.click());
  expect(state.logout).toHaveBeenCalledTimes(1);
});

it("re-checks access by replacing the location with the platform root", () => {
  const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
  render();
  act(() => button("rework.platformAccess.denied.check")!.click());
  expect(replace.mock.calls).toEqual([["/"]]);
  // A deployment served under a base path goes back to that base.
  state.basename = "/fred/";
  render();
  act(() => button("rework.platformAccess.denied.check")!.click());
  expect(replace.mock.lastCall).toEqual(["/fred/"]);
  expect(open).not.toHaveBeenCalled();
  replace.mockRestore();
});

it("hides the request action when no support link is configured", () => {
  state.support = "";
  render();
  expect(button("rework.platformAccess.denied.request")).toBeUndefined();
  expect(button("rework.platformAccess.denied.check")).toBeDefined();
  expect(button("rework.platformAccess.signOut")).toBeDefined();
  expect(steps()).toHaveLength(2);
});
