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

// Sort orders for the team agents list. Kept out of the page for the same
// reason as the search predicate: testable without mounting the container.

import type { ManagedAgentInstanceSummary } from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { getCurrentUserPreferences, persistUserPreference } from "../../../../app/userPreferences";

export type AgentSortValue = "name" | "created_at:desc" | "updated_at:desc";

export const DEFAULT_AGENT_SORT: AgentSortValue = "name";

const SORT_VALUES: readonly AgentSortValue[] = ["name", "created_at:desc", "updated_at:desc"];

export function getStoredAgentSort(): AgentSortValue {
  const stored = getCurrentUserPreferences().agent_sort;
  return SORT_VALUES.find((value) => value === stored) ?? DEFAULT_AGENT_SORT;
}

export function storeAgentSort(sort: AgentSortValue): void {
  persistUserPreference({ agent_sort: sort });
}

/** Epoch millis, or null when the field is absent or unparseable. */
function timestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/** Most recent first, with anything undated last whichever way the pair falls. */
function byRecency(a: string | null | undefined, b: string | null | undefined): number {
  const left = timestamp(a);
  const right = timestamp(b);
  if (left === right) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return right - left;
}

/**
 * Returns a new array — the caller's list is RTK Query state, frozen in dev,
 * so sorting it in place would throw.
 *
 * Alphabetical uses `localeCompare` with base sensitivity so accents and case
 * fall where a reader expects ("Élan" next to "Elan", not after "Zulu").
 */
export function sortAgents<T extends Pick<ManagedAgentInstanceSummary, "display_name" | "created_at" | "updated_at">>(
  instances: T[],
  sort: AgentSortValue,
): T[] {
  const sorted = [...instances];
  switch (sort) {
    case "created_at:desc":
      return sorted.sort((a, b) => byRecency(a.created_at, b.created_at));
    case "updated_at:desc":
      return sorted.sort((a, b) => byRecency(a.updated_at, b.updated_at));
    case "name":
    default:
      return sorted.sort((a, b) =>
        (a.display_name ?? "").localeCompare(b.display_name ?? "", undefined, { sensitivity: "base" }),
      );
  }
}
