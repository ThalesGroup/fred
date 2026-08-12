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
import { displayPath, relativeDirSegments } from "./droppedPaths";

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
