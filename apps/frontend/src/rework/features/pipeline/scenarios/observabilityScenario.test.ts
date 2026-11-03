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

import { describe, expect, it } from "vitest";
import { collect, signal } from "./fakePlatform";
import { observabilityScenario, type ObservabilityDeps } from "./observabilityScenario";

function deps(overrides: Partial<ObservabilityDeps> = {}): ObservabilityDeps {
  return {
    kpis: [{ id: "kpi-sessions", title: "Sessions", read: async () => 3 }],
    searchHealth: async () => "green",
    metricsTargets: async () => [{ job: "agents", up: true }],
    ...overrides,
  };
}

async function run(d: ObservabilityDeps) {
  const r = collect();
  await observabilityScenario(d, r.report, signal);
  return r;
}

describe("observabilityScenario", () => {
  it("passes when every KPI and backend answers", async () => {
    const r = await run(deps());
    expect(r.steps.map((s) => s.status)).toEqual(["passed", "passed", "passed"]);
  });

  it("skips backends the deployment does not run", async () => {
    const r = await run(deps({ searchHealth: async () => null, metricsTargets: async () => null }));
    expect(r.status("search-backend")).toBe("skipped");
    expect(r.status("metrics-backend")).toBe("skipped");
  });

  it("fails a red cluster, a down target and an unreadable KPI", async () => {
    const r = await run(
      deps({
        kpis: [{ id: "kpi-messages", title: "Messages", read: async () => Promise.reject(new Error("HTTP 500")) }],
        searchHealth: async () => "red",
        metricsTargets: async () => [
          { job: "agents", up: false },
          { job: "agents", up: false },
          { job: "knowledge", up: true },
        ],
      }),
    );
    expect(r.status("kpi-messages")).toBe("failed");
    expect(r.status("search-backend")).toBe("failed");
    expect(r.steps.find((s) => s.id === "metrics-backend")?.error).toBe("down: agents");
  });
});
