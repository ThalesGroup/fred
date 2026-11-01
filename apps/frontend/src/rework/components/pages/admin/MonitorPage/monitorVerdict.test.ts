// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { expect, it } from "vitest";
import type {
  ContainerStatus,
  RecentEvent,
  ServiceStatus,
  Snapshot,
} from "../../../../../slices/monitor/monitorOpenApi";
import { monitorVerdict } from "./monitorVerdict";

const service = (name: string, state: ServiceStatus["state"] = "ready"): ServiceStatus => ({
  name,
  state,
  kind: "Deployment",
  desired: 1,
  ready: state === "ready" ? 1 : 0,
});
const container = (last_exit_at?: string | null, pod = "control-plane-abc"): ContainerStatus => ({
  pod,
  container: "api",
  init: false,
  phase: "Running",
  ready: true,
  restarts: 100,
  last_exit_at,
  last_exit_reason: "OOMKilled",
});
const event = (object = "Pod/control-plane-abc", observed_at = "2026-10-31T11:59:00Z"): RecentEvent => ({
  uid: object + observed_at,
  object,
  observed_at,
  severity: "Warning",
  reason: "BackOff",
  message: `Warning for ${object} at ${observed_at}`,
  count: 2,
});
const snapshot = (overrides: Partial<Snapshot> = {}): Snapshot => ({
  namespace: "fred",
  observed_at: "2026-10-31T12:00:00Z",
  event_window_seconds: 3600,
  unavailable_sources: [],
  truncated_sources: [],
  events_limited: false,
  services: [service("control-plane")],
  containers: [],
  events: [],
  ...overrides,
});

it("returns ready names and counts inactive services without findings", () => {
  expect(
    monitorVerdict(snapshot({ services: [service("api"), service("ui"), service("worker", "inactive")] })),
  ).toEqual({
    level: "ok",
    findings: [],
    ready: ["api", "ui"],
    inactive: 1,
  });
});

it.each([
  ["degraded", "error"],
  ["updating", "warning"],
  ["unknown", "warning"],
] as const)("reports %s as %s", (state, level) => {
  expect(monitorVerdict(snapshot({ services: [service("control-plane", state)] }))).toEqual({
    level,
    findings: [{ service: "control-plane", level, kind: state, ready: 0, desired: 1 }],
    ready: [],
    inactive: 0,
  });
});

it.each([
  ["2026-10-31T11:59:00Z", "warning"],
  ["2026-10-31T11:00:00Z", "ok"],
  ["2026-10-31T10:59:59Z", "ok"],
  [undefined, "ok"],
  [null, "ok"],
] as const)("uses the snapshot window for exit %s regardless of cumulative restarts", (at, level) => {
  const verdict = monitorVerdict(snapshot({ containers: [container(at)] }));
  expect(verdict.level).toBe(level);
  expect(verdict.findings).toEqual(
    level === "warning"
      ? [{ service: "control-plane", level: "warning", kind: "restarted", at, reason: "OOMKilled" }]
      : [],
  );
});

it("keeps only the most recent restart per service across pods and containers", () => {
  const at = "2026-10-31T11:59:00Z";
  const verdict = monitorVerdict(
    snapshot({
      containers: [
        container("2026-10-31T11:10:00Z"),
        { ...container(at, "control-plane-def"), last_exit_reason: "Error" },
        container("2026-10-31T11:30:00Z"),
      ],
    }),
  );
  expect(verdict.findings).toEqual([
    { service: "control-plane", level: "warning", kind: "restarted", at, reason: "Error" },
  ]);
});

it("does not create findings from Warning events or an event display limit alone", () => {
  expect(monitorVerdict(snapshot({ events: [event()], events_limited: true }))).toEqual({
    level: "ok",
    findings: [],
    ready: ["control-plane"],
    inactive: 0,
  });
});

it("attaches only the latest Warning to every finding for that service", () => {
  const latest = event("Deployment/control-plane", "2026-10-31T11:59:30Z");
  const verdict = monitorVerdict(
    snapshot({
      services: [service("control-plane", "degraded")],
      containers: [container("2026-10-31T11:59:00Z")],
      events: [latest, event(), { ...event("Deployment/control-plane", "2026-10-31T12:00:00Z"), severity: "Normal" }],
    }),
  );
  expect(verdict.level).toBe("error");
  expect(verdict.findings).toHaveLength(2);
  expect(verdict.findings.map((finding) => finding.event)).toEqual([latest.message, latest.message]);
});

it("matches the longest service prefix for both pods and events", () => {
  const warning = event("Pod/temporal-ui-abc");
  const verdict = monitorVerdict(
    snapshot({
      services: [service("temporal"), service("temporal-ui")],
      containers: [container("2026-10-31T11:59:00Z", "temporal-ui-abc")],
      events: [warning],
    }),
  );
  expect(verdict.findings).toEqual([
    expect.objectContaining({ service: "temporal-ui", kind: "restarted", event: warning.message }),
  ]);
});

it("accepts exact pod names but requires a hyphen for a prefix match", () => {
  const verdict = monitorVerdict(
    snapshot({
      containers: [container("2026-10-31T11:59:00Z", "control-plane")],
      events: [event("Pod/control-planeother")],
    }),
  );
  expect(verdict.findings[0].service).toBe("control-plane");
  expect(verdict.findings[0].event).toBeUndefined();
});

it("retains unmatched restarts as a global warning without attaching unrelated events", () => {
  const verdict = monitorVerdict(
    snapshot({
      containers: [container("2026-10-31T11:59:00Z", "other-abc")],
      events: [event("Pod/other-abc")],
    }),
  );
  expect(verdict.level).toBe("warning");
  expect(verdict.findings).toEqual([expect.objectContaining({ service: "", kind: "restarted" })]);
  expect(verdict.findings[0].event).toBeUndefined();
});

it.each<Partial<Snapshot>>([{ unavailable_sources: ["events"] }, { truncated_sources: ["pods"] }])(
  "reports partial data for %o",
  (sources) => {
    const verdict = monitorVerdict(snapshot(sources));
    expect(verdict.level).toBe("warning");
    expect(verdict.findings).toEqual([
      { service: "", level: "warning", kind: "partial", sources: Object.values(sources)[0] },
    ]);
  },
);

it("merges unavailable and truncated sources without duplicates", () => {
  const verdict = monitorVerdict(snapshot({ unavailable_sources: ["events"], truncated_sources: ["events", "pods"] }));
  expect(verdict.findings[0].sources).toEqual(["events", "pods"]);
});

it("sorts errors first, then service names, without mutating the snapshot", () => {
  const input = snapshot({
    services: [service("z", "updating"), service("b", "degraded"), service("a", "unknown"), service("a", "degraded")],
    unavailable_sources: ["pods"],
  });
  const original = structuredClone(input);
  expect(monitorVerdict(input).findings.map(({ level, service }) => [level, service])).toEqual([
    ["error", "a"],
    ["error", "b"],
    ["warning", ""],
    ["warning", "a"],
    ["warning", "z"],
  ]);
  expect(input).toEqual(original);
});
