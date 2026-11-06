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
import type { TaskState } from "../../../../features/tasks/taskTypes";
import type { StepReport } from "../../../../features/pipeline/types";

export function overallState(steps: StepReport[], isRunning: boolean): TaskState | "partial" {
  if (isRunning || steps.length === 0) return "running";
  if (steps.some((s) => s.status === "failed")) return "failed";
  // Map an all-skipped run to the task badge's cancelled state.
  // Individual steps retain their skipped status.
  const validated = steps.some((s) => s.status === "passed" || s.status === "running");
  if (!validated && steps.some((s) => s.status === "skipped")) return "cancelled";
  if (steps.some((s) => s.status === "skipped" && !s.optional)) return "partial";
  return "succeeded";
}

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
export function buildReport(steps: StepReport[], title?: string): string {
  return [...(title ? [title] : []), `Self-test: ${counts(steps)}`, "", ...stepLines(steps)].join("\n");
}

export interface ReportSection {
  title: string;
  steps: StepReport[];
  startedAt?: Date;
}

export interface ReportGroup {
  title: string;
  sections: ReportSection[];
}

/** One report for every family run so far, dated and tied to the page origin. */
export function buildCombinedReport(
  sections: ReportSection[],
  origin: string,
  at: Date,
  manual: ReportSection[] = [],
  groups?: ReportGroup[],
): string {
  const ran = sections.filter((s) => s.steps.length > 0);
  const all = ran.flatMap((s) => s.steps);
  return [
    `Self-test report — ${origin} — ${at.toISOString()}`,
    `${manual.length ? "Standard tests" : "Total"}: ${counts(all)}`,
    ...(groups
      ? groups.flatMap((group) => [
          "",
          `# ${group.title}: ${counts(group.sections.flatMap((section) => section.steps))}`,
          ...group.sections.flatMap((section) => [
            "",
            `## ${section.title}: ${section.steps.length ? counts(section.steps) : "Not run"}`,
            ...stepLines(section.steps),
          ]),
        ])
      : (manual.length ? sections : ran).flatMap((s) => [
          "",
          `## ${s.title}: ${s.steps.length ? counts(s.steps) : "Not run"}`,
          ...stepLines(s.steps),
        ])),
    ...(manual.length ? ["", `Manual tests: ${counts(manual.flatMap((s) => s.steps))}`] : []),
    ...manual.flatMap((s) => [
      "",
      `## ${s.title}: ${s.steps.length ? counts(s.steps) : "Not run"}`,
      ...(s.startedAt ? [s.startedAt.toISOString()] : []),
      ...stepLines(s.steps),
    ]),
  ].join("\n");
}
