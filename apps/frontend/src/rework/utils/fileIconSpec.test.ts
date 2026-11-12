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
import { fileIconSpec } from "./fileIconSpec.ts";

describe("fileIconSpec", () => {
  it("maps pdf to picture_as_pdf in error", () => {
    expect(fileIconSpec("report.pdf")).toEqual({ type: "picture_as_pdf", color: "var(--error)" });
  });

  it.each(["docx", "doc", "odt", "md", "html", "txt"])("maps .%s (Word/Texte) to article in tertiary", (extension) => {
    expect(fileIconSpec(`notes.${extension}`)).toEqual({ type: "article", color: "var(--tertiary)" });
  });

  it.each(["xlsx", "xls", "ods", "csv"])("maps .%s (Excel/CSV) to table in success", (extension) => {
    expect(fileIconSpec(`plan.${extension}`)).toEqual({ type: "table", color: "var(--success)" });
  });

  it.each(["ppt", "pptx", "odp"])("maps .%s (PowerPoint) to slideshow in warning", (extension) => {
    expect(fileIconSpec(`deck.${extension}`)).toEqual({ type: "slideshow", color: "var(--warning)" });
  });

  it("reads the extension case-insensitively, after the last dot", () => {
    expect(fileIconSpec("Q3.Budget.CSV").type).toBe("table");
  });

  it("trusts the name over a generic media type sent by the browser", () => {
    expect(fileIconSpec("07-staffing-plan.csv", "application/octet-stream").type).toBe("table");
    expect(fileIconSpec("01-overview.md", "").type).toBe("article");
  });

  it("uses the media type only to tell an image apart", () => {
    expect(fileIconSpec("photo.png", "image/png")).toEqual({ type: "image", color: "var(--on-surface-muted)" });
    expect(fileIconSpec("scan", "application/pdf").type).toBe("draft");
  });

  it("falls back to draft in on-surface-muted for unknown or missing extensions", () => {
    const other = { type: "draft", color: "var(--on-surface-muted)" };
    expect(fileIconSpec("archive.zip")).toEqual(other);
    expect(fileIconSpec("README")).toEqual(other);
    expect(fileIconSpec(".env")).toEqual(other);
  });
});
