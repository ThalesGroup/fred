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
import { previewVersionKey, wordTemplateErrorKind } from "./sessionDocument";
import {
  addTemplateFiles,
  labelFromFilename,
  readTemplateLibrary,
  removeTemplateEntry,
  templateLibraryRowProblems,
} from "./templateLibrary";

const file = (name: string) => new File(["x"], name);

describe("word_template template library", () => {
  it("prefills names from file names and pairs new entries with staged files", () => {
    const state = addTemplateFiles({ entries: [{ label: "Stored", template_key: "k1" }], files: [] }, [
      file("Rapport_annuel  v2.docx"),
      file("Note.DOCX"),
    ]);
    expect(state.entries.map((e) => e.label)).toEqual(["Stored", "Rapport annuel v2", "Note"]);
    expect(labelFromFilename("a_b.docx")).toBe("a b");
    // Removing the second NEW entry drops the second staged file, not the first.
    const after = removeTemplateEntry(state, 2);
    expect(after.files.map((f) => f.name)).toEqual(["Rapport_annuel  v2.docx"]);
    // Removing a stored entry keeps every staged file.
    expect(removeTemplateEntry(state, 0).files).toHaveLength(2);
  });

  it("flags empty and duplicate names the way the backend folds them", () => {
    const entries = readTemplateLibrary([{ label: "Modèle A" }, { label: "  modele   a " }, { label: "" }, "junk"]);
    expect(templateLibraryRowProblems(entries)).toEqual(["duplicateLabel", "duplicateLabel", "missingLabel"]);
    expect(readTemplateLibrary(undefined)).toEqual([]);
  });
});

describe("word_template session document", () => {
  it("maps 404/409/502 to distinct messages using the backend detail", () => {
    expect(wordTemplateErrorKind({ status: 404 })).toBe("noDocument");
    expect(
      wordTemplateErrorKind({ status: 409, detail: "The session's edits could not be applied to its template." }),
    ).toBe("editsNotApplicable");
    expect(wordTemplateErrorKind({ status: 409, detail: "The session's Word template could not be retrieved." })).toBe(
      "templateUnavailable",
    );
    expect(wordTemplateErrorKind({ status: 502 })).toBe("conversion");
    expect(wordTemplateErrorKind({})).toBe("generic");
  });

  it("changes the preview key on each edit", () => {
    expect(previewVersionKey({ session_id: "s" })).toBeNull();
    const a = previewVersionKey({ session_id: "s", template_key: "k", edit_count: 1, updated_at: "t1" });
    const b = previewVersionKey({ session_id: "s", template_key: "k", edit_count: 2, updated_at: "t2" });
    expect(a).not.toBe(b);
  });
});
