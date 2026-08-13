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

// The relative-path readers behind structure-preserving folder drops: they must
// see the same directory chain whether the file came from file-selector's drop
// traversal (`path`, "/batch/sub/a.pdf") or a webkitdirectory input
// (`webkitRelativePath`, "batch/sub/a.pdf"), and see NO chain for a file
// dropped or picked on its own ("./a.pdf", bare name, or nothing).

import { describe, expect, it } from "vitest";
import {
  MAX_FOLDER_DEPTH,
  displayPath,
  exceedsMaxFolderDepth,
  folderPathDepth,
  relativeDirSegments,
} from "./droppedPaths";

function fileWith(name: string, extra: { path?: string; webkitRelativePath?: string } = {}): File {
  const file = new File(["x"], name);
  for (const [key, value] of Object.entries(extra)) {
    Object.defineProperty(file, key, { value });
  }
  return file;
}

describe("relativeDirSegments", () => {
  it("reads the directory chain from a dropped-directory path", () => {
    expect(relativeDirSegments(fileWith("a.pdf", { path: "/batch/sub/a.pdf" }))).toEqual(["batch", "sub"]);
  });

  it("reads the directory chain from a webkitdirectory relative path", () => {
    expect(relativeDirSegments(fileWith("a.pdf", { webkitRelativePath: "batch/a.pdf" }))).toEqual(["batch"]);
  });

  it("sees no chain for a file dropped on its own", () => {
    expect(relativeDirSegments(fileWith("a.pdf", { path: "./a.pdf" }))).toEqual([]);
    expect(relativeDirSegments(fileWith("a.pdf", { path: "a.pdf" }))).toEqual([]);
    expect(relativeDirSegments(fileWith("a.pdf"))).toEqual([]);
  });

  it("drops empty and whitespace-only segments", () => {
    expect(relativeDirSegments(fileWith("a.pdf", { path: "//batch//  /a.pdf" }))).toEqual(["batch"]);
  });
});

describe("displayPath", () => {
  it("prefixes the directory chain when there is one, plain name otherwise", () => {
    expect(displayPath(fileWith("a.pdf", { path: "/batch/sub/a.pdf" }))).toBe("batch/sub/a.pdf");
    expect(displayPath(fileWith("a.pdf"))).toBe("a.pdf");
  });
});

describe("folderPathDepth", () => {
  it("counts destination segments, with 0 for the corpus root", () => {
    expect(folderPathDepth("CIR/Sub")).toBe(2);
    expect(folderPathDepth("CIR")).toBe(1);
    expect(folderPathDepth("")).toBe(0);
    expect(folderPathDepth(undefined)).toBe(0);
    expect(folderPathDepth(null)).toBe(0);
  });
});

describe("exceedsMaxFolderDepth", () => {
  const chain = (depth: number) => `/${Array.from({ length: depth }, (_, i) => `d${i}`).join("/")}/a.pdf`;

  it("accepts a file landing exactly at MAX_FOLDER_DEPTH", () => {
    expect(exceedsMaxFolderDepth(fileWith("a.pdf", { path: chain(MAX_FOLDER_DEPTH) }), 0)).toBe(false);
    expect(exceedsMaxFolderDepth(fileWith("a.pdf", { path: chain(MAX_FOLDER_DEPTH - 3) }), 3)).toBe(false);
  });

  it("rejects a file one level past the cap", () => {
    expect(exceedsMaxFolderDepth(fileWith("a.pdf", { path: chain(MAX_FOLDER_DEPTH + 1) }), 0)).toBe(true);
  });

  it("counts the destination folder's own depth toward the cap", () => {
    // The same dropped chain passes at the root but not inside a deep folder.
    const file = fileWith("a.pdf", { path: chain(MAX_FOLDER_DEPTH) });
    expect(exceedsMaxFolderDepth(file, 0)).toBe(false);
    expect(exceedsMaxFolderDepth(file, 1)).toBe(true);
  });

  it("never rejects a loose file dropped into a valid folder", () => {
    expect(exceedsMaxFolderDepth(fileWith("a.pdf"), MAX_FOLDER_DEPTH)).toBe(false);
  });
});
