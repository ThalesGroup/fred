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

/** A readable message for an Error or a generated-client failure (`{ status, data }`). */
export function describeError(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (err && typeof err === "object" && "status" in err) {
    const { status, data, error } = err as { status: unknown; data?: unknown; error?: unknown };
    const body = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
    const detail = body ?? error;
    const text =
      detail === undefined || detail === null ? "" : typeof detail === "string" ? detail : JSON.stringify(detail);
    return text ? `HTTP ${String(status)}: ${text}` : `HTTP ${String(status)}`;
  }
  return String(err);
}

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
      report({ id, title, status: "failed", error: describeError(err), optional, durationMs });
    }
    return null;
  }
}
