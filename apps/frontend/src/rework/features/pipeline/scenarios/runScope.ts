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
import type { Reporter } from "../types";

/** Run-scoped names: fixtures never collide with real content, and teardown targets only this run's ids. */
export interface RunScope {
  token: string;
  name: (base: string) => string;
}

export function newRunScope(): RunScope {
  const token = (globalThis.crypto?.randomUUID?.() ?? `${Math.random()}`).replace(/[^a-z0-9]/gi, "").slice(0, 8);
  return { token, name: (base) => `${base}-${token}` };
}

/** Optional teardown step: skipped when nothing was created, so it never fails a clean run on its own. */
export async function cleanup(
  report: Reporter,
  id: string,
  title: string,
  created: string | null,
  remove: (id: string) => Promise<void>,
  verifyGone: (id: string) => Promise<void>,
): Promise<void> {
  await runStep(
    report,
    id,
    title,
    async () => {
      if (!created) throw new SkipStep("nothing was created");
      await remove(created);
      await verifyGone(created);
      return { value: undefined, detail: `deleted ${created}` };
    },
    { optional: true },
  );
}

/** The HTTP status carried by an RTK Query or fetch failure, or null. */
export function statusOf(error: unknown): number | null {
  if (error && typeof error === "object" && "status" in error) {
    const status = (error as { status: unknown }).status;
    return typeof status === "number" ? status : null;
  }
  return null;
}

/** Resolves to the status of a call expected to be refused; throws when it succeeds. */
export async function expectRefused(
  call: () => Promise<unknown>,
  label: string,
  allowedStatuses: readonly number[] = [403, 404],
): Promise<number> {
  try {
    await call();
  } catch (error) {
    const status = statusOf(error);
    if (status === null) throw error;
    if (!allowedStatuses.includes(status))
      throw new Error(`${label}: HTTP ${status}, expected ${allowedStatuses.join(" or ")}`);
    return status;
  }
  throw new Error(`${label} succeeded; expected a refusal`);
}
