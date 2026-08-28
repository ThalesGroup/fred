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

// Per-device "recently viewed teams" for the Home nav-panel team switcher.
// Deliberately client-only (localStorage): a switcher convenience, not synced
// across devices — so it needs no backend, no endpoint and no DB migration.
// Every read/write is guarded: a blocked or full storage degrades to "no
// recency" (falls back to alphabetical) rather than throwing.

const RECENCY_KEY = "fred.teamRecency";
const SORT_MODE_KEY = "fred.teamSortMode";

export type TeamSortMode = "recent" | "alpha";
type RecencyMap = Record<string, number>;

function readRecency(): RecencyMap {
  try {
    const raw = localStorage.getItem(RECENCY_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    return parsed && typeof parsed === "object" ? (parsed as RecencyMap) : {};
  } catch {
    return {};
  }
}

/** `{ teamId: lastVisitedEpochMs }` — empty when nothing was recorded yet. */
export function getTeamRecency(): RecencyMap {
  return readRecency();
}

/** Stamp a team as visited "now". Called on entry into any `/team/:id` route. */
export function recordTeamVisit(teamId: string): void {
  if (!teamId) return;
  try {
    const map = readRecency();
    map[teamId] = Date.now();
    localStorage.setItem(RECENCY_KEY, JSON.stringify(map));
  } catch {
    // Storage blocked or full — recency is best-effort, so just skip.
  }
}

export function getTeamSortMode(): TeamSortMode {
  try {
    return localStorage.getItem(SORT_MODE_KEY) === "alpha" ? "alpha" : "recent";
  } catch {
    return "recent";
  }
}

export function setTeamSortMode(mode: TeamSortMode): void {
  try {
    localStorage.setItem(SORT_MODE_KEY, mode);
  } catch {
    // Persisting the preference is best-effort.
  }
}
