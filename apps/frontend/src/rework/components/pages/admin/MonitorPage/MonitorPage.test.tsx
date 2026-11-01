// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
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
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { resolvedLanguage: "en" } }),
}));
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
  Object.assign(h.access, { isAdmin: true, isLoading: false, isFetching: false, isError: false });
  Object.assign(h.query, { isError: false, isFetching: false, error: undefined });
  h.query.currentData = {
    namespace: "fred",
    observed_at: "2026-10-31T12:00:00Z",
    event_window_seconds: 3600,
    unavailable_sources: [],
    truncated_sources: [],
    events_limited: false,
    services: [{ name: "control-plane", kind: "Deployment", desired: 1, ready: 1, state: "ready" }],
    containers: [
      {
        pod: "control-plane-abc",
        container: "api",
        init: false,
        phase: "Running",
        ready: true,
        restarts: 2,
        last_exit_reason: "OOMKilled",
        last_exit_at: "2026-10-31T11:59:00Z",
      },
    ],
    events: [
      {
        uid: "event-1",
        observed_at: "2026-10-31T11:59:00Z",
        severity: "Warning",
        reason: "BackOff",
        object: "Pod/control-plane-abc",
        message: "Container restarted",
        count: 2,
      },
    ],
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

it("renders ready services alongside restart evidence and recent events", () => {
  render();
  expect(host.textContent).toContain("control-plane");
  expect(host.textContent).toContain("OOMKilled");
  expect(host.textContent).toContain("Container restarted");
  expect(h.request).toHaveBeenCalledWith(undefined, expect.objectContaining({ skip: false, pollingInterval: 15000 }));
  act(() => window.dispatchEvent(new Event("focus")));
  expect(h.query.refetch).toHaveBeenCalledOnce();
});

it("does not query or disclose cached data to an organization admin", () => {
  h.access.isAdmin = false;
  render();
  expect(h.request).toHaveBeenCalledWith(undefined, expect.objectContaining({ skip: true }));
  expect(host.textContent).toContain("rework.monitor.forbidden");
  expect(host.textContent).not.toContain("OOMKilled");
  expect(host.textContent).not.toContain("control-plane");
});

it("hides the previous snapshot when a refresh loses permission", () => {
  render();
  h.query.isError = true;
  h.query.error = { status: 403 };
  render();
  expect(host.textContent).toContain("rework.monitor.forbidden");
  expect(host.textContent).not.toContain("OOMKilled");
});

it("keeps available services visible while marking failed and truncated sources", () => {
  h.query.currentData!.events = [];
  h.query.currentData!.unavailable_sources = ["events"];
  h.query.currentData!.truncated_sources = ["pods"];
  render();
  expect(host.textContent).toContain("control-plane");
  expect(host.textContent).toContain("rework.monitor.partial");
  expect(host.textContent).toContain("rework.monitor.truncated");
  expect(host.textContent).toContain("rework.monitor.dataUnavailable");
  expect(host.textContent).not.toContain("rework.monitor.noEvents");
});
