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

// What an import left behind when the tab was closed in the middle of it.
//
// A file the server never received exists nowhere but in this browser, and the
// store goes with the page. So the names and where they were headed are
// written down as the import runs, and struck off as each file gets there.
// Whatever is still listed on the next visit is what did not arrive.
//
// Deliberately not the files themselves: they cannot be stored, which is why
// the offer on return is to pick them again, not to resume on its own.

import type { UploadMode } from "./importRun";

const STORAGE_KEY = "fred.imports.unfinished";

/** Long enough to fold one import's strike-offs into a single write, short
 *  enough that a tab lost outside `pagehide` costs at most this much. */
const FLUSH_DELAY_MS = 250;

/** After this, an unfinished import is archaeology rather than something the
 *  user meant to finish, and offering it back is noise. Dropped on read, so a
 *  record left behind by a browser that never came back cannot pile up. */
const RECORD_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export interface UnfinishedFile {
  /** The panel entry this file had. Identity is the entry, never the name: one
   *  import can carry the same leaf name to two folders, and striking off by
   *  name would let the first arrival account for both. */
  entryId: string;
  filename: string;
  /** The team this import was headed for — the panel belongs to one team. */
  teamId: string | null;
  uploadMode: UploadMode;
  /** The destination and options the file was sent with, so picking it again
   *  sends it to the same place the same way. */
  requestMetadata: Record<string, unknown>;
  /** Why it never got there, when we were told. Absent means the page went
   *  away before anything could be said — which is its own kind of cause. */
  cause?: string;
  /** When the import was started, for `RECORD_TTL_MS`. Absent on a record
   *  written before this field existed; those are kept, not dropped. */
  notedAt?: number;
}

/** Storage can be unavailable (private window, blocked site data) and its
 *  contents can be anything. Neither is worth failing an import over. */
// The record is read and rewritten once per batch as an import starts and once
// per file as it lands. Parsing it each time made a large import quadratic in
// its own size, on the main thread, before the first byte moved — so the list
// is held here and localStorage is the durable copy, not the source consulted.
// Another tab writing it invalidates ours (the listener below).
let cache: UnfinishedFile[] | null = null;

function read(): UnfinishedFile[] {
  if (cache) return cache;
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return (cache = []);
    const cutoff = Date.now() - RECORD_TTL_MS;
    return (cache = parsed.filter(
      (entry): entry is UnfinishedFile =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as UnfinishedFile).entryId === "string" &&
        typeof (entry as UnfinishedFile).filename === "string" &&
        typeof (entry as UnfinishedFile).requestMetadata === "object" &&
        ((entry as UnfinishedFile).notedAt ?? Infinity) > cutoff,
    ));
  } catch {
    return (cache = []);
  }
}

function persist(files: UnfinishedFile[]): void {
  try {
    if (files.length === 0) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
  } catch {
    // Nothing to do and nothing worth telling the user: the import itself is
    // unaffected, only the account of it if this page goes away.
  }
}

let flushHandle: number | null = null;

/** Coalesce the strike-offs of one import into a single write. `pagehide`
 *  below is what makes losing the tab in between still cost nothing. */
function scheduleFlush(): void {
  if (flushHandle !== null) return;
  flushHandle = window.setTimeout(flush, FLUSH_DELAY_MS);
}

/** Never writes an empty list it did not build. A null cache means another tab
 *  rewrote the record and ours was dropped — persisting `[]` then would take
 *  that tab's in-flight import down with it, which is the one thing this
 *  record exists to prevent. Our own pending strike-offs are the cheaper loss:
 *  they cost a file being offered again, not a file being forgotten. */
function flush(): void {
  flushHandle = null;
  if (cache !== null) persist(cache);
}

function flushNow(): void {
  if (flushHandle === null) return;
  window.clearTimeout(flushHandle);
  flush();
}

/** Drop a pending flush without running it — for a caller about to write the
 *  whole record itself, which would otherwise write it twice. */
function cancelFlush(): void {
  if (flushHandle === null) return;
  window.clearTimeout(flushHandle);
  flushHandle = null;
}

if (typeof window !== "undefined") {
  // Another tab rewrote the record; ours is stale.
  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY) cache = null;
  });
  window.addEventListener("pagehide", flushNow);
}

/** Drop the in-memory copy, so the next read goes back to storage. For a test
 *  that seeds `localStorage` the way a previous page load would have. */
export function forgetCachedRecord(): void {
  cache = null;
}

/** Files that were left in the air last time. A copy: the caller holds it in
 *  state while the record keeps changing underneath. */
export function unfinishedImports(): UnfinishedFile[] {
  return [...read()];
}

/** Note files as on their way. Written before the first byte moves, because an
 *  interruption two seconds in must leave the same trace as one at the end. */
export function noteImportStarted(files: UnfinishedFile[]): void {
  const current = read();
  const known = new Set(current.map((entry) => entry.entryId));
  const notedAt = Date.now();
  cache = [...current, ...files.filter((entry) => !known.has(entry.entryId)).map((entry) => ({ ...entry, notedAt }))];
  // Written through, not scheduled: the promise this record makes is that an
  // interruption two seconds in leaves the same trace as one at the very end.
  cancelFlush();
  persist(cache);
}

/** Note why a file never got there, keeping it listed. A failure is not an
 *  arrival: the entry stays so the next visit can say what went wrong instead
 *  of only that the file is missing. */
export function noteImportFailed(entryId: string, cause: string): void {
  cache = read().map((entry) => (entry.entryId === entryId ? { ...entry, cause } : entry));
  scheduleFlush();
}

/** Strike a file off: it got there, or the user gave up on it. */
export function noteImportSettled(entryId: string): void {
  cache = read().filter((entry) => entry.entryId !== entryId);
  scheduleFlush();
}

/** Give up on named files only — never on the whole record, which may be
 *  carrying an import that is running right now. */
export function forgetUnfinishedImports(entryIds: string[]): void {
  const dropped = new Set(entryIds);
  cache = read().filter((entry) => !dropped.has(entry.entryId));
  persist(cache);
}
