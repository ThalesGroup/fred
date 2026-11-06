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

import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";

export interface ObservabilityDeps {
  /** KPI presets the analytics pages read, over the last day. */
  kpis: Array<{ id: string; title: string; read: () => Promise<number> }>;
  /** Cluster status, or null when the deployment has no search backend. */
  searchHealth: () => Promise<string | null>;
  /** Scrape targets, or null when the deployment has no metrics backend. */
  metricsTargets: () => Promise<Array<{ job: string; up: boolean }> | null>;
}

/** Observability family: read-only, and a missing optional backend is skipped, never failed. */
export const observabilityScenario: Scenario<ObservabilityDeps> = async (deps, report) => {
  for (const kpi of deps.kpis) {
    await runStep(report, kpi.id, kpi.title, async () => ({
      value: undefined,
      detail: `${await kpi.read()} point(s) over the last day`,
    }));
  }
  await runStep(report, "search-backend", "The search cluster is healthy", async () => {
    const status = await deps.searchHealth();
    if (status === null) throw new SkipStep("this deployment has no search cluster");
    if (status === "red") throw new Error("the search cluster is red");
    return { value: undefined, detail: status };
  });
  await runStep(report, "metrics-backend", "Every metrics target is up", async () => {
    const targets = await deps.metricsTargets();
    if (targets === null) throw new SkipStep("this deployment has no metrics backend");
    const down = targets.filter((t) => !t.up).map((t) => t.job);
    if (down.length) throw new Error(`down: ${[...new Set(down)].join(", ")}`);
    return { value: undefined, detail: `${targets.length} target(s) up` };
  });
};
