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

// Coverage for downloadManyAsZip (RFC KNOWLEDGE-WORKSPACE-REWORK-RFC.md
// §13.13): 0 files is a no-op, exactly 1 file downloads directly (no zip
// built), 2+ files are zipped into one archive, and same-named files across
// rows get disambiguated instead of one silently overwriting the other in
// the zip. Real JSZip is used (not mocked) — it's pure JS, and reading the
// produced archive back is stronger coverage than asserting call shapes on
// a mocked zip API.

import JSZip from "jszip";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { downloadManyAsZip } from "./downloadUtils.tsx";

let createdUrls: Blob[] = [];
let clickedDownloads: string[] = [];

beforeEach(() => {
  createdUrls = [];
  clickedDownloads = [];
  vi.spyOn(URL, "createObjectURL").mockImplementation((blob: Blob) => {
    createdUrls.push(blob);
    return `blob:mock-${createdUrls.length}`;
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clickedDownloads.push(this.download);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function blob(text: string): Blob {
  return new Blob([text], { type: "text/plain" });
}

describe("downloadManyAsZip", () => {
  it("does nothing for an empty selection", async () => {
    await downloadManyAsZip([], "resources.zip");

    expect(clickedDownloads).toEqual([]);
    expect(createdUrls).toEqual([]);
  });

  it("downloads a single file directly, without building a zip", async () => {
    const fileBlob = blob("hello");
    await downloadManyAsZip([{ filename: "notes.txt", fetchBlob: async () => fileBlob }], "resources.zip");

    expect(clickedDownloads).toEqual(["notes.txt"]);
    expect(createdUrls).toEqual([fileBlob]);
  });

  it("zips 2+ files into a single archive named after zipFilename", async () => {
    await downloadManyAsZip(
      [
        { filename: "a.txt", fetchBlob: async () => blob("A") },
        { filename: "b.txt", fetchBlob: async () => blob("B") },
      ],
      "resources.zip",
    );

    expect(clickedDownloads).toEqual(["resources.zip"]);
    expect(createdUrls).toHaveLength(1);

    const zip = await JSZip.loadAsync(createdUrls[0]);
    expect(Object.keys(zip.files).sort()).toEqual(["a.txt", "b.txt"]);
    expect(await zip.file("a.txt")!.async("string")).toBe("A");
    expect(await zip.file("b.txt")!.async("string")).toBe("B");
  });

  it("keeps every file's bytes when zipping several (no 0-byte entries)", async () => {
    // Guards the Firefox 0-byte regression: JSZip read Blobs lazily during
    // generateAsync, dropping all but one entry to empty. Every entry must carry
    // its full content.
    const contents = { "a.txt": "alpha", "b.txt": "beta", "c.txt": "gamma" };
    await downloadManyAsZip(
      Object.entries(contents).map(([filename, text]) => ({ filename, fetchBlob: async () => blob(text) })),
      "resources.zip",
    );

    const zip = await JSZip.loadAsync(createdUrls[0]);
    expect(Object.keys(zip.files).sort()).toEqual(["a.txt", "b.txt", "c.txt"]);
    for (const [name, text] of Object.entries(contents)) {
      expect(await zip.file(name)!.async("string")).toBe(text);
    }
  });

  it("disambiguates same-named files instead of one overwriting the other", async () => {
    await downloadManyAsZip(
      [
        { filename: "notes.txt", fetchBlob: async () => blob("first") },
        { filename: "notes.txt", fetchBlob: async () => blob("second") },
      ],
      "resources.zip",
    );

    const zip = await JSZip.loadAsync(createdUrls[0]);
    expect(Object.keys(zip.files).sort()).toEqual(["notes (2).txt", "notes.txt"]);
    expect(await zip.file("notes.txt")!.async("string")).toBe("first");
    expect(await zip.file("notes (2).txt")!.async("string")).toBe("second");
  });
});
