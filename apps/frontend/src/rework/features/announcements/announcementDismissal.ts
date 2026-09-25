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

// Per-browser record of which announcement banners a user has closed.
//
// Deliberately client-side: the control-plane has no user-preferences store,
// and the worst outcome of losing this is a banner showing again. The key
// carries the announcement's `content_version`, which the backend moves on an
// edit and on a relaunch (a disabled announcement switched back on). Both make
// the banner reappear for everyone who dismissed the previous run — what an
// operator fixing a date, or re-running a notice, actually wants.

const STORAGE_KEY = "fred.announcements.dismissed";

/**
 * `id@version` — a bumped version no longer matches a stored entry.
 *
 * Exported because in-session dismissal state must key on exactly this: keying
 * it on the id alone would leave an edited announcement suppressed for the
 * rest of an already-open tab, which is the one case the version key exists
 * to cover.
 */
export function dismissalKey(id: string, contentVersion: number): string {
  return `${id}@${contentVersion}`;
}

/**
 * Read the dismissed set.
 *
 * Every access is guarded: `localStorage` throws outright in a private window
 * with site data blocked, and returns junk if something else wrote the key.
 * Any failure degrades to "nothing was ever dismissed" — the banner shows,
 * which is the safe direction for an announcement.
 */
function readDismissed(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((entry): entry is string => typeof entry === "string"));
  } catch {
    return new Set();
  }
}

/**
 * Snapshot the dismissed set once, then test many announcements against it.
 *
 * Callers that filter a list must use this rather than `isDismissed` per item:
 * every read parses the stored JSON, and `localStorage` is synchronous on the
 * main thread.
 */
export function readDismissedSet(): ReadonlySet<string> {
  return readDismissed();
}

export function isDismissedIn(dismissed: ReadonlySet<string>, id: string, contentVersion: number): boolean {
  return dismissed.has(dismissalKey(id, contentVersion));
}

export function isDismissed(id: string, contentVersion: number): boolean {
  return isDismissedIn(readDismissed(), id, contentVersion);
}

/**
 * Record a dismissal, dropping any older entry for the same announcement.
 *
 * Pruning by id keeps the list from growing one entry per edit per
 * announcement over the life of a browser profile.
 */
export function markDismissed(id: string, contentVersion: number): void {
  const kept = [...readDismissed()].filter((entry) => !entry.startsWith(`${id}@`));
  kept.push(dismissalKey(id, contentVersion));
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(kept));
  } catch {
    // Storage unavailable or full: the banner stays dismissed for this page
    // view (the stack holds it in React state) and returns on the next load.
  }
}

/** Test seam — clears the stored set without reaching into the key name. */
export function clearDismissed(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do: an unreadable store is already "nothing dismissed".
  }
}
