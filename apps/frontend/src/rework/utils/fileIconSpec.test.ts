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
    expect(fileIconSpec("pdf")).toEqual({ type: "picture_as_pdf", color: "var(--error)" });
  });

  it.each(["docx", "md", "html", "txt"])("maps %s (Word/Texte) to article in tertiary", (fileType) => {
    expect(fileIconSpec(fileType)).toEqual({ type: "article", color: "var(--tertiary)" });
  });

  it.each(["xlsx", "csv"])("maps %s (Excel/CSV) to table in success", (fileType) => {
    expect(fileIconSpec(fileType)).toEqual({ type: "table", color: "var(--success)" });
  });

  it.each(["ppt", "pptx"])("maps %s (PowerPoint) to slideshow in warning", (fileType) => {
    expect(fileIconSpec(fileType)).toEqual({ type: "slideshow", color: "var(--warning)" });
  });

  it("falls back to draft in on-surface-muted for unknown or missing file types", () => {
    expect(fileIconSpec("other")).toEqual({ type: "draft", color: "var(--on-surface-muted)" });
    expect(fileIconSpec(undefined)).toEqual({ type: "draft", color: "var(--on-surface-muted)" });
    expect(fileIconSpec(null)).toEqual({ type: "draft", color: "var(--on-surface-muted)" });
  });
});
