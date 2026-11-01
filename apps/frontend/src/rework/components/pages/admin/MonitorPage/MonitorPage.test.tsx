// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createInstance } from "i18next";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";
import type { Snapshot } from "../../../../../slices/monitor/monitorOpenApi";

const h = vi.hoisted(() => ({
  access: { isAdmin: true, isLoading: false, isFetching: false, isError: false, currentData: {}, refetch: vi.fn() },
  query: {
    currentData: undefined as Snapshot | undefined,
    isError: false,
    isFetching: false,
    error: undefined as { status: number } | undefined,
    refetch: vi.fn(),
  },
  request: vi.fn(),
}));
const i18n = createInstance();
void i18n.init({ lng: "en", fallbackLng: "en", resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: i18n.t.bind(i18n), i18n }) }));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => h.access }));
vi.mock("../../../../../slices/monitor/monitorOpenApi", () => ({
  useMonitorStatusQuery: (arg: unknown, options: unknown) => {
    h.request(arg, options);
    return h.query;
  },
}));

import MonitorPage from "./MonitorPage";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
  void i18n.changeLanguage("en");
  Object.assign(h.access, { isAdmin: true, isLoading: false, isFetching: false, isError: false, currentData: {} });
  Object.assign(h.query, { isError: false, isFetching: false, error: undefined });
  h.query.currentData = {
    namespace: "private-namespace",
    observed_at: "2026-10-31T12:00:00Z",
    event_window_seconds: 3600,
    unavailable_sources: [],
    truncated_sources: [],
    events_limited: false,
    services: [{ name: "control-plane", kind: "Deployment", desired: 1, ready: 1, state: "ready" }],
    containers: [],
    events: [],
  };
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const render = () => act(() => root.render(<MonitorPage />));
const chip = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>('[role="group"] button')).find(
    (button) => button.querySelector("[title]")?.getAttribute("title") === name,
  )!;
const openComponent = (name: string) => {
  const button = chip(name);
  expect(button.getAttribute("aria-expanded")).toBe("false");
  act(() => button.click());
  expect(button.getAttribute("aria-expanded")).toBe("true");
  expect(button.getAttribute("aria-controls")).toBe("monitor-component-detail");
  return host.querySelector("#monitor-component-detail")!;
};

it.each([
  ["ready", "success", "All systems operational · 1 service ready"],
  ["updating", "warning", "Needs attention · 1 item"],
  ["degraded", "error", "Problem · 1 item"],
  ["inactive", "on-surface-retreat", "All systems operational · 0 services ready"],
] as const)("renders %s as a colored component chip with details on click", (state, color, title) => {
  h.query.currentData!.services[0].state = state;
  render();
  expect(host.querySelector("h2")!.textContent).toBe(title);
  expect(chip("control-plane").getAttribute("data-color")).toBe(color);
  expect(chip("control-plane").textContent).toContain(en.rework.monitor.states[state]);
  expect(host.querySelector("#monitor-component-detail")).toBeNull();
  const detail = openComponent("control-plane");
  expect(detail.textContent).toContain("Deployment · 1/1 replicas ready");
  expect(host.textContent).not.toContain("private-namespace");
  expect(host.querySelector("table")).toBeNull();
});

it("switches between components and closes details on a second click or Escape", () => {
  h.query.currentData!.services.push({ name: "frontend", kind: "Deployment", state: "ready", desired: 2, ready: 2 });
  render();
  openComponent("control-plane");
  expect(openComponent("frontend").textContent).toContain("2/2 replicas ready");
  expect(chip("control-plane").getAttribute("aria-expanded")).toBe("false");
  act(() => chip("frontend").click());
  expect(host.querySelector("#monitor-component-detail")).toBeNull();
  openComponent("frontend");
  act(() => {
    chip("frontend").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
  expect(host.querySelector("#monitor-component-detail")).toBeNull();
});

it("keeps healthy components visible alongside degraded ones", () => {
  h.query.currentData!.services[0].state = "degraded";
  h.query.currentData!.services.push({ name: "frontend", kind: "Deployment", state: "ready", desired: 1, ready: 1 });
  render();
  expect(chip("control-plane").getAttribute("data-color")).toBe("error");
  expect(chip("frontend").getAttribute("data-color")).toBe("success");
  expect(openComponent("frontend").querySelector("li")).toBeNull();
});

it("refreshes selected details from the current snapshot and hides a removed component", () => {
  render();
  openComponent("control-plane");
  h.query.currentData = {
    ...h.query.currentData!,
    services: [{ name: "control-plane", kind: "Deployment", state: "degraded", desired: 1, ready: 0 }],
  };
  render();
  expect(chip("control-plane").getAttribute("data-color")).toBe("error");
  expect(host.querySelector("#monitor-component-detail")!.textContent).toContain("0/1 replicas ready");
  h.query.currentData = { ...h.query.currentData, services: [] };
  render();
  expect(host.querySelector("#monitor-component-detail")).toBeNull();
  expect(host.textContent).not.toContain("control-plane");
});

it("keeps polling, window focus and manual refresh", () => {
  render();
  expect(h.request).toHaveBeenCalledWith(undefined, {
    skip: false,
    pollingInterval: 15000,
    refetchOnMountOrArgChange: true,
  });
  expect(host.querySelector('[role="status"]')!.textContent).toContain("refreshed every 15 s");
  act(() => window.dispatchEvent(new Event("focus")));
  expect(h.query.refetch).toHaveBeenCalledOnce();
  const refresh = Array.from(host.querySelectorAll("button")).find((button) => button.textContent === "Refresh")!;
  act(() => refresh.click());
  expect(h.query.refetch).toHaveBeenCalledTimes(2);
  h.query.isFetching = true;
  render();
  expect(refresh.disabled).toBe(true);
  expect(host.querySelector('[role="status"]')!.textContent).toBe("Refreshing…");
});

it("shows refreshing during the first snapshot request", () => {
  h.query.currentData = undefined;
  h.query.isFetching = true;
  render();
  expect(host.querySelector('[role="status"]')!.textContent).toBe("Refreshing…");
  expect(host.querySelector('[aria-expanded]')).toBeNull();
});

it("renders restart evidence and its Warning below the finding", () => {
  h.query.currentData!.containers = [{
    pod: "control-plane-abc",
    container: "api",
    init: false,
    phase: "Running",
    ready: true,
    restarts: 2,
    last_exit_reason: "OOMKilled",
    last_exit_at: "2026-10-31T11:59:00Z",
  }];
  h.query.currentData!.events = [{
    uid: "event-1",
    observed_at: "2026-10-31T11:59:00Z",
    severity: "Warning",
    reason: "BackOff",
    object: "Pod/control-plane-abc",
    message: "Container restarted",
    count: 2,
  }];
  render();
  expect(chip("control-plane").getAttribute("data-color")).toBe("warning");
  expect(host.textContent).not.toContain("OOMKilled");
  const detail = openComponent("control-plane");
  expect(detail.querySelectorAll("li")).toHaveLength(1);
  expect(detail.textContent).toContain("Restarted at");
  expect(detail.textContent).toContain("(OOMKilled)");
  expect(detail.querySelector("li > p")!.textContent).toBe('"Container restarted"');
});

it("shows a single partial finding for failed and truncated sources", () => {
  h.query.currentData!.unavailable_sources = ["events"];
  h.query.currentData!.truncated_sources = ["pods"];
  render();
  expect(chip("Global findings").getAttribute("data-color")).toBe("warning");
  expect(chip("control-plane").getAttribute("data-color")).toBe("success");
  const detail = openComponent("Global findings");
  expect(detail.querySelectorAll("li")).toHaveLength(1);
  expect(detail.textContent).toContain("Incomplete data: Events, Pods");
});

it.each(["en", "fr"])("shows all components, including inactive ones, in %s", (language) => {
  void i18n.changeLanguage(language);
  h.query.currentData!.services.push(
    { name: "frontend", kind: "Deployment", state: "ready", desired: 1, ready: 1 },
    { name: "worker", kind: "Deployment", state: "inactive", desired: 0, ready: 0 },
  );
  render();
  expect(host.querySelector("h2")!.textContent).toContain(
    language === "fr" ? "Tout fonctionne · 2 services prêts" : "All systems operational · 2 services ready",
  );
  expect(host.querySelectorAll('[role="group"] button')).toHaveLength(3);
  expect(chip("worker").textContent).toContain(language === "fr" ? "Inactif" : "Inactive");
  expect(openComponent("worker").textContent).toContain("0/0");
});

it("does not query or disclose cached data to an organization admin", () => {
  h.access.isAdmin = false;
  render();
  expect(h.request).toHaveBeenCalledWith(undefined, expect.objectContaining({ skip: true }));
  expect(host.querySelector('[role="alert"]')!.textContent).toContain(en.rework.monitor.forbidden);
  expect(host.textContent).not.toContain("control-plane");
});

it.each([
  [403, en.rework.monitor.forbidden],
  [503, en.rework.monitor.authorizationUnavailable],
] as const)("hides the previous snapshot on access failure %s", (status, message) => {
  render();
  openComponent("control-plane");
  h.query.isError = true;
  h.query.error = { status };
  render();
  expect(host.querySelector('[role="alert"]')!.textContent).toContain(message);
  expect(host.textContent).not.toContain("control-plane");
  expect(host.querySelector('[aria-expanded]')).toBeNull();
});

it("shows unknown status and removes protected data when the monitor is unreachable", () => {
  render();
  openComponent("control-plane");
  h.query.isError = true;
  h.query.error = { status: 502 };
  render();
  const card = host.querySelector('[aria-live="polite"] > [data-color]')!;
  expect(card.getAttribute("data-color")).toBe("warning");
  expect(card.querySelector("button")!.textContent).toContain(en.rework.monitor.unreachable);
  act(() => card.querySelector("button")!.click());
  expect(card.querySelector("button")!.getAttribute("aria-expanded")).toBe("true");
  expect(card.textContent).toContain(en.rework.monitor.unavailable);
  expect(host.querySelector("#monitor-component-detail")).toBeNull();
  expect(host.textContent).not.toContain("control-plane");
});

it("shows an authority notice with the existing retry action and no protected data", () => {
  h.access.isAdmin = false;
  h.access.isError = true;
  render();
  const notice = host.querySelector('[role="alert"]')!;
  expect(notice.textContent).toContain(en.rework.provisioning.authorityUnavailable);
  expect(host.textContent).not.toContain("control-plane");
  const retry = notice.querySelector("button")!;
  expect(retry.textContent).toBe(en.rework.provisioning.retryAuthority);
  act(() => retry.click());
  expect(h.access.refetch).toHaveBeenCalledOnce();
});
