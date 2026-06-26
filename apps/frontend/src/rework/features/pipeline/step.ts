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

import type { Reporter } from "./types";

/** Throw from a step body to report it as skipped (a precondition was missing). */
export class SkipStep extends Error {}

/**
 * Run one named step: report running, then passed / failed / skipped with timing.
 * Returns the step's value, or null if it failed or was skipped — so a scenario
 * keeps going and every step is reported (teardown still runs in a finally).
 */
export async function runStep<T>(
  report: Reporter,
  id: string,
  title: string,
  body: () => Promise<{ value: T; detail?: string }>,
  options?: { optional?: boolean },
): Promise<T | null> {
  const optional = options?.optional ?? false;
  const start = performance.now();
  report({ id, title, status: "running", optional });
  try {
    const { value, detail } = await body();
    report({ id, title, status: "passed", detail, optional, durationMs: Math.round(performance.now() - start) });
    return value;
  } catch (err) {
    const durationMs = Math.round(performance.now() - start);
    if (err instanceof SkipStep) {
      report({ id, title, status: "skipped", detail: err.message, optional, durationMs });
    } else {
      report({ id, title, status: "failed", error: (err as Error)?.message ?? String(err), optional, durationMs });
    }
    return null;
  }
}
