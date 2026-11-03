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
import type { StepReport } from "../../../../features/pipeline/types";

function counts(steps: StepReport[]): string {
  const passed = steps.filter((s) => s.status === "passed").length;
  const failed = steps.filter((s) => s.status === "failed").length;
  const skipped = steps.filter((s) => s.status === "skipped").length;
  return `${passed} passed, ${failed} failed, ${skipped} skipped, ${steps.length} steps`;
}

function stepLines(steps: StepReport[]): string[] {
  return steps.map((step, i) => {
    const dur = step.durationMs != null ? ` (${step.durationMs} ms)` : "";
    const info = step.error ? ` — ERROR: ${step.error}` : step.detail ? ` — ${step.detail}` : "";
    return `${i + 1}. [${step.status.toUpperCase()}] ${step.title}${info}${dur}`;
  });
}

/** Plain-text report of one run, as copied from its panel. */
export function buildReport(steps: StepReport[]): string {
  return [`Self-test: ${counts(steps)}`, "", ...stepLines(steps)].join("\n");
}

export interface ReportSection {
  title: string;
  steps: StepReport[];
}

/** One report for every family run so far, dated and tied to the page origin. */
export function buildCombinedReport(sections: ReportSection[], origin: string, at: Date): string {
  const ran = sections.filter((s) => s.steps.length > 0);
  const all = ran.flatMap((s) => s.steps);
  return [
    `Self-test report — ${origin} — ${at.toISOString()}`,
    `Total: ${counts(all)}`,
    ...ran.flatMap((s) => ["", `## ${s.title}: ${counts(s.steps)}`, ...stepLines(s.steps)]),
  ].join("\n");
}
