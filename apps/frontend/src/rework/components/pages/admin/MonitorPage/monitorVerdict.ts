// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { RecentEvent, Snapshot, Source } from "../../../../../slices/monitor/monitorOpenApi";

export type VerdictLevel = "ok" | "warning" | "error";
export interface Finding {
  service: string;
  level: "warning" | "error";
  kind: "degraded" | "updating" | "unknown" | "restarted" | "partial";
  ready?: number;
  desired?: number;
  reason?: string | null;
  at?: string | null;
  event?: string;
  sources?: Source[];
}
export interface Verdict {
  level: VerdictLevel;
  findings: Finding[];
  ready: string[];
  inactive: number;
}

export function monitorVerdict(snapshot: Snapshot): Verdict {
  const findings: Finding[] = [];
  const ready: string[] = [];
  let inactive = 0;
  const names = snapshot.services.map((service) => service.name).sort((a, b) => b.length - a.length);
  const serviceFor = (object: string) => {
    const name = object.slice(object.lastIndexOf("/") + 1);
    return names.find((service) => name === service || name.startsWith(`${service}-`));
  };
  for (const service of snapshot.services) {
    if (service.state === "ready") ready.push(service.name);
    else if (service.state === "inactive") inactive++;
    else {
      findings.push({
        service: service.name,
        level: service.state === "degraded" ? "error" : "warning",
        kind: service.state,
        ready: service.ready,
        desired: service.desired,
      });
    }
  }
  const cutoff = Date.parse(snapshot.observed_at) - snapshot.event_window_seconds * 1000;
  const restarts = new Map<string, Finding>();
  for (const container of snapshot.containers) {
    const at = container.last_exit_at;
    // Keep unmatched restarts as a global warning, without inventing a service.
    const service = serviceFor(container.pod) ?? "";
    if (!at || !(Date.parse(at) > cutoff)) continue;
    const previous = restarts.get(service);
    if (!previous || Date.parse(at) > Date.parse(previous.at!)) {
      restarts.set(service, { service, level: "warning", kind: "restarted", at, reason: container.last_exit_reason });
    }
  }
  findings.push(...restarts.values());
  const sources = [...new Set([...snapshot.unavailable_sources, ...snapshot.truncated_sources])];
  if (sources.length) findings.push({ service: "", level: "warning", kind: "partial", sources });

  const events = new Map<string, RecentEvent>();
  for (const event of snapshot.events) {
    const service = serviceFor(event.object);
    if (event.severity !== "Warning" || !service) continue;
    const previous = events.get(service);
    if (!previous || Date.parse(event.observed_at) > Date.parse(previous.observed_at)) events.set(service, event);
  }
  for (const finding of findings) {
    const event = events.get(finding.service);
    if (event) finding.event = event.message;
  }
  findings.sort((a, b) => a.level.localeCompare(b.level) || a.service.localeCompare(b.service));
  return {
    level: findings.some((finding) => finding.level === "error") ? "error" : findings.length ? "warning" : "ok",
    findings,
    ready,
    inactive,
  };
}
