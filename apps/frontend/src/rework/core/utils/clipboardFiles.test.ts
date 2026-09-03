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

import { describe, expect, it } from "vitest";
import { clipboardAttachments, clipboardFileName, clipboardPrefersFiles } from "./clipboardFiles";

const PASTED_AT = new Date("2026-09-03T14:25:30.000Z");

function file(name: string, mime = "image/png", content = "x"): File {
  return new File([content], name, { type: mime });
}

function clipboard(files: File[], text = ""): DataTransfer {
  return {
    files: files as unknown as FileList,
    getData: (type: string) => (type === "text/plain" ? text : ""),
  } as unknown as DataTransfer;
}

describe("clipboardPrefersFiles", () => {
  it("prefers the files when the clipboard carries no text", () => {
    expect(clipboardPrefersFiles("")).toBe(true);
    expect(clipboardPrefersFiles("  \n ")).toBe(true);
  });

  it("prefers the text when the clipboard carries real text (Excel pastes a rendered PNG too)", () => {
    expect(clipboardPrefersFiles("Q1\t120\nQ2\t180")).toBe(false);
  });

  it("treats the paths a file manager leaves behind as no text", () => {
    expect(clipboardPrefersFiles("file:///home/simon/report.pdf")).toBe(true);
    expect(clipboardPrefersFiles("/home/simon/report.pdf\n/home/simon/notes.md")).toBe(true);
    expect(clipboardPrefersFiles("C:\\Users\\simon\\report.pdf")).toBe(true);
    expect(clipboardPrefersFiles("/home/simon/Documents/Q3 report.pdf")).toBe(true);
    expect(clipboardPrefersFiles("\\\\server\\share\\Q3 report.pdf")).toBe(true);
  });

  it("ignores the marker lines a file manager puts in front of the copied paths", () => {
    expect(clipboardPrefersFiles("x-special/nautilus-clipboard\ncopy\nfile:///home/simon/report.pdf")).toBe(true);
  });
});

describe("clipboardFileName", () => {
  it("keeps a name the source actually gave the file", () => {
    expect(clipboardFileName("report.pdf", "application/pdf", PASTED_AT, 0)).toBe("report.pdf");
  });

  it("names screenshots by paste time so two pastes stay distinguishable", () => {
    expect(clipboardFileName("image.png", "image/png", PASTED_AT, 0)).toBe("pasted-20260903-142530-000.png");
  });

  it("keeps files of one paste apart and falls back to the mime type for the extension", () => {
    expect(clipboardFileName("", "image/webp", PASTED_AT, 1)).toBe("pasted-20260903-142530-000-2.webp");
  });

  it("maps the mime types whose extension is not the subtype", () => {
    expect(clipboardFileName("", "image/svg+xml", PASTED_AT, 0)).toBe("pasted-20260903-142530-000.svg");
    expect(clipboardFileName("", "image/jpeg", PASTED_AT, 0)).toBe("pasted-20260903-142530-000.jpg");
    expect(clipboardFileName("", "application/vnd.ms-excel", PASTED_AT, 0)).toBe("pasted-20260903-142530-000.xls");
    expect(clipboardFileName("", "application/pdf; charset=binary", PASTED_AT, 0)).toBe(
      "pasted-20260903-142530-000.pdf",
    );
  });

  it("keeps an extension for a format Fred has no processor for, so ingestion reports it like any upload", () => {
    // No allow-list here: the 400 must come from the backend registry, not from
    // a file the composer quietly stripped of its extension.
    expect(clipboardFileName("", "application/x-tar", PASTED_AT, 0)).toBe("pasted-20260903-142530-000.tar");
    expect(clipboardFileName("", "audio/mpeg", PASTED_AT, 0)).toBe("pasted-20260903-142530-000.mpeg");
  });

  it("separates two pastes taken within the same second", () => {
    const first = clipboardFileName("image.png", "image/png", new Date("2026-09-03T14:25:30.120Z"), 0);
    const second = clipboardFileName("image.png", "image/png", new Date("2026-09-03T14:25:30.480Z"), 0);
    expect(first).not.toBe(second);
  });
});

describe("clipboardAttachments", () => {
  it("returns nothing when the paste carries no file", () => {
    expect(clipboardAttachments(null)).toEqual([]);
    expect(clipboardAttachments(clipboard([], "plain text"))).toEqual([]);
  });

  it("attaches a pasted document under its own name", () => {
    const attached = clipboardAttachments(clipboard([file("report.pdf", "application/pdf")]), PASTED_AT);
    expect(attached.map((f) => f.name)).toEqual(["report.pdf"]);
  });

  it("renames a pasted screenshot and preserves its content", async () => {
    const attached = clipboardAttachments(clipboard([file("image.png", "image/png", "png-bytes")]), PASTED_AT);
    expect(attached).toHaveLength(1);
    expect(attached[0].name).toBe("pasted-20260903-142530-000.png");
    expect(attached[0].type).toBe("image/png");
    expect(await attached[0].text()).toBe("png-bytes");
  });

  it("leaves a rich-text paste alone even though it carries an image", () => {
    expect(clipboardAttachments(clipboard([file("image.png")], "Q1\t120"), PASTED_AT)).toEqual([]);
  });

  it("attaches every file of a multi-file copy, each under its own name", () => {
    const attached = clipboardAttachments(
      clipboard(
        [file("report.pdf", "application/pdf"), file("notes.md", "text/markdown"), file("chart.png", "image/png")],
        "x-special/nautilus-clipboard\ncopy\nfile:///home/simon/report.pdf\nfile:///home/simon/notes.md\nfile:///home/simon/chart.png",
      ),
      PASTED_AT,
    );
    expect(attached.map((f) => f.name)).toEqual(["report.pdf", "notes.md", "chart.png"]);
  });

  it("keeps several generically named files of one paste distinguishable", () => {
    const attached = clipboardAttachments(clipboard([file("image.png"), file("image.png"), file("")]), PASTED_AT);
    expect(attached.map((f) => f.name)).toEqual([
      "pasted-20260903-142530-000.png",
      "pasted-20260903-142530-000-2.png",
      "pasted-20260903-142530-000-3.png",
    ]);
  });

  it("drops empty entries so a stray directory paste is not attached", () => {
    expect(clipboardAttachments(clipboard([file("folder", "", "")]), PASTED_AT)).toEqual([]);
  });
});
