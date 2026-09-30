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
}

/** Storage can be unavailable (private window, blocked site data) and its
 *  contents can be anything. Neither is worth failing an import over. */
function read(): UnfinishedFile[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is UnfinishedFile =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as UnfinishedFile).entryId === "string" &&
        typeof (entry as UnfinishedFile).filename === "string" &&
        typeof (entry as UnfinishedFile).requestMetadata === "object",
    );
  } catch {
    return [];
  }
}

function write(files: UnfinishedFile[]): void {
  try {
    if (files.length === 0) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
  } catch {
    // Nothing to do and nothing worth telling the user: the import itself is
    // unaffected, only the account of it if this page goes away.
  }
}

/** Files that were left in the air last time. */
export function unfinishedImports(): UnfinishedFile[] {
  return read();
}

/** Note files as on their way. Written before the first byte moves, because an
 *  interruption two seconds in must leave the same trace as one at the end. */
export function noteImportStarted(files: UnfinishedFile[]): void {
  const known = new Set(read().map((entry) => entry.entryId));
  write([...read(), ...files.filter((entry) => !known.has(entry.entryId))]);
}

/** Strike a file off: it got there, or the user gave up on it. */
export function noteImportSettled(entryId: string): void {
  write(read().filter((entry) => entry.entryId !== entryId));
}

/** Give up on named files only — never on the whole record, which may be
 *  carrying an import that is running right now. */
export function forgetUnfinishedImports(entryIds: string[]): void {
  const dropped = new Set(entryIds);
  write(read().filter((entry) => !dropped.has(entry.entryId)));
}
