// @vitest-environment happy-dom
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

// The record is the only trace a file ever existed once the tab is gone, so
// what it is keyed by decides whether a file can be silently lost.

import { beforeEach, describe, expect, it } from "vitest";
import {
  forgetCachedRecord,
  forgetUnfinishedImports,
  noteImportSettled,
  noteImportStarted,
  unfinishedImports,
} from "./unfinishedImports";

const entry = (entryId: string, filename: string, tag: string) => ({
  entryId,
  filename,
  teamId: "team-1",
  uploadMode: "process" as const,
  requestMetadata: { tags: [tag] },
});

beforeEach(() => {
  window.localStorage.clear();
  // The record is held in memory between reads; a fresh page load is what
  // each of these starts from.
  forgetCachedRecord();
});

describe("unfinishedImports", () => {
  it("keeps one record per file, not per name", () => {
    // A dropped tree with a README in two subfolders is two files, two
    // destinations, two things that can be lost independently.
    noteImportStarted([entry("e1", "README.md", "tag-a"), entry("e2", "README.md", "tag-b")]);

    expect(unfinishedImports()).toHaveLength(2);
  });

  it("does not let one file's arrival account for its namesake", () => {
    noteImportStarted([entry("e1", "README.md", "tag-a"), entry("e2", "README.md", "tag-b")]);

    noteImportSettled("e1");

    // Keyed by name, this deleted both, and the second file was lost with no
    // trace on the next visit — the exact case the record exists for.
    expect(unfinishedImports().map((e) => e.entryId)).toEqual(["e2"]);
  });

  it("ignores a file already recorded, so a retry does not double it", () => {
    noteImportStarted([entry("e1", "a.pdf", "tag-a")]);
    noteImportStarted([entry("e1", "a.pdf", "tag-a")]);

    expect(unfinishedImports()).toHaveLength(1);
  });

  it("gives up only on what it was asked to give up on", () => {
    noteImportStarted([entry("old-1", "lost.pdf", "tag-a"), entry("new-1", "running.pdf", "tag-a")]);

    // Dismissing last visit's leftovers must not throw away the import that
    // is running right now.
    forgetUnfinishedImports(["old-1"]);

    expect(unfinishedImports().map((e) => e.entryId)).toEqual(["new-1"]);
  });

  it("survives storage holding something else entirely", () => {
    window.localStorage.setItem("fred.imports.unfinished", "not json");
    expect(unfinishedImports()).toEqual([]);

    window.localStorage.setItem("fred.imports.unfinished", '[{"nope": 1}]');
    expect(unfinishedImports()).toEqual([]);
  });
});
