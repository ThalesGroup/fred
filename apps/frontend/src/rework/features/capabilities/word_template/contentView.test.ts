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
import type { CellView, RowView } from "./api/wordTemplateCapabilityOpenApi";
import {
  cellWriteOperation,
  changedRemotely,
  classifyEditError,
  editRequest,
  escapeInlineMarkdown,
  hasPendingChange,
  inlineEditable,
  isEditablePiece,
  replaceTextOperations,
  segmentOperation,
  setTextOperation,
  shownValue,
  storyOf,
  tableLayout,
  typeInDraft,
  unescapeInlineMarkdown,
} from "./contentView";

describe("set_text escaping", () => {
  it("escapes the literal Markdown characters and round-trips", () => {
    const plain = "PRJ_0001 *draft* `x` C:\\temp";
    const escaped = escapeInlineMarkdown(plain);
    expect(escaped).toBe("PRJ\\_0001 \\*draft\\* \\`x\\` C:\\\\temp");
    expect(unescapeInlineMarkdown(escaped)).toBe(plain);
  });

  it("edits an unformatted place as plain text and escapes it on save", () => {
    const editable = inlineEditable({ text: "Lot_2 * 3", markdown: "Lot\\_2 \\* 3" });
    expect(editable).toEqual({ mode: "plain", value: "Lot_2 * 3" });
    expect(setTextOperation("P4", "Lot_3 * 3", editable.mode)).toEqual({
      op: "set_text",
      address: "P4",
      text: "Lot\\_3 \\* 3",
    });
  });

  it("keeps a formatted place's Markdown as is", () => {
    const editable = inlineEditable({ text: "Total HT", markdown: "**Total** HT" });
    expect(editable).toEqual({ mode: "markdown", value: "**Total** HT" });
    expect(setTextOperation("T1.R2.C1", "**Total** TTC", editable.mode).text).toBe("**Total** TTC");
  });

  it("treats a marker after an escaped backslash as formatting", () => {
    expect(inlineEditable({ markdown: "a\\\\*b*" }).mode).toBe("markdown");
    expect(inlineEditable({ markdown: "a\\*b" }).mode).toBe("plain");
  });

  it("falls back to escaping the text when no Markdown is given", () => {
    expect(inlineEditable({ text: "a_b" })).toEqual({ mode: "plain", value: "a_b" });
  });
});

describe("replace_text pieces", () => {
  const place = {
    address: "F1.P1",
    edit: "replace_text" as const,
    pieces: [{ text: "Page " }, { text: "3", field: true }, { text: " " }, { text: "Confidentiel" }],
  };

  it("never edits field or blank pieces", () => {
    expect(place.pieces.map(isEditablePiece)).toEqual([true, false, false, true]);
  });

  it("sends one replace_text per changed piece, find = its current text", () => {
    expect(replaceTextOperations(place, { 0: "Page n° ", 1: "9", 3: "Confidentiel" })).toEqual([
      { op: "replace_text", address: "F1.P1", find: "Page ", replace: "Page n° " },
    ]);
  });
});

describe("write / insert_after", () => {
  it("completes a segment's ready-made write with the editor's Markdown", () => {
    const segment = { edit: { op: "write", from: "P3", to: "P7" } };
    expect(segmentOperation(segment, "- un&#x20;\n- deux\n\n")).toEqual({
      op: "write",
      from: "P3",
      to: "P7",
      markdown: "- un \n- deux",
    });
  });

  it("fills an empty chapter body through insert_after its heading", () => {
    const segment = { edit: { op: "insert_after", address: "P2" } };
    expect(segmentOperation(segment, "Texte")).toEqual({ op: "insert_after", address: "P2", markdown: "Texte" });
  });

  it("writes a multi-paragraph cell from its address", () => {
    expect(cellWriteOperation("T1.R1.C2", "a\n\nb\n")).toEqual({ op: "write", from: "T1.R1.C2", markdown: "a\n\nb" });
  });

  it("makes the batch on the view's seq", () => {
    const ops = [{ op: "remove", from: "T2" }];
    expect(editRequest(7, ops)).toEqual({ base_seq: 7, operations: ops });
  });
});

describe("tableLayout", () => {
  const cell = (address: string, col: number, extra: Partial<CellView> = {}): CellView => ({ address, col, ...extra });

  it("keeps merged cells and skips the columns a vertical merge covers", () => {
    const rows: RowView[] = [
      { address: "T1.R1", cells: [cell("T1.R1.C1", 1, { row_span: 2 }), cell("T1.R1.C2", 2, { col_span: 2 })] },
      { address: "T1.R2", cells: [cell("T1.R2.C2", 2), cell("T1.R2.C3", 3)] },
      { address: "T1.R3", cells: [cell("T1.R3.C1", 1), cell("T1.R3.C2", 2), cell("T1.R3.C3", 3)] },
    ];
    const layout = tableLayout({ rows, n_cols: 3 });
    expect(layout.map((r) => r.map((s) => (s.kind === "cell" ? s.cell.address : `gap${s.span}`)))).toEqual([
      ["T1.R1.C1", "T1.R1.C2"],
      ["T1.R2.C2", "T1.R2.C3"],
      ["T1.R3.C1", "T1.R3.C2", "T1.R3.C3"],
    ]);
  });

  it("fills uncovered grid columns with gaps", () => {
    const rows: RowView[] = [
      { address: "T1.R1", cells: [cell("T1.R1.C1", 1), cell("T1.R1.C2", 2), cell("T1.R1.C3", 3)] },
      { address: "T1.R2", cells: [cell("T1.R2.C3", 3)] },
      { address: "T1.R3", cells: [cell("T1.R3.C1", 1)] },
    ];
    const layout = tableLayout({ rows, n_cols: 3 });
    expect(layout[1]).toEqual([
      { kind: "gap", span: 2 },
      { kind: "cell", cell: rows[1].cells![0] },
    ]);
    expect(layout[2]).toEqual([
      { kind: "cell", cell: rows[2].cells![0] },
      { kind: "gap", span: 2 },
    ]);
  });
});

describe("classifyEditError", () => {
  it("409: the document changed (reload)", () => {
    expect(classifyEditError({ status: 409, data: { detail: { message: "changed", seq: 5 } } })).toEqual({
      kind: "stale",
      seq: 5,
    });
  });

  it("a 409 without seq is a failure, not a reload", () => {
    const err = { status: 409, data: { detail: "The template could not be retrieved." } };
    expect(classifyEditError(err)).toEqual({ kind: "other", message: "The template could not be retrieved." });
  });

  it("422: lists the problems", () => {
    const err = { status: 422, data: { detail: { message: "rejected", problems: ["op 1: no such address T9"] } } };
    expect(classifyEditError(err)).toEqual({
      kind: "rejected",
      message: "rejected",
      problems: ["op 1: no such address T9"],
    });
  });

  it("422 from request validation: FastAPI's list of errors", () => {
    const err = { status: 422, data: { detail: [{ msg: "field required" }] } };
    expect(classifyEditError(err)).toMatchObject({ kind: "rejected", problems: ["field required"] });
  });

  it("anything else is a plain failure", () => {
    expect(classifyEditError({ status: "FETCH_ERROR", error: "TypeError: Failed to fetch" })).toEqual({
      kind: "other",
      message: "TypeError: Failed to fetch",
    });
    expect(classifyEditError({ status: 500, data: { detail: "boom" } })).toEqual({ kind: "other", message: "boom" });
  });
});

describe("drafts vs. the AI's edits", () => {
  it("keeps the typed text across a refresh and flags the AI's change of the same place", () => {
    let draft = typeInDraft(null, "Version A", "Version A + mine");
    draft = typeInDraft(draft, "Version B (AI)", "Version A + mine!");
    expect(draft).toEqual({ value: "Version A + mine!", original: "Version A" });
    expect(shownValue(draft, "Version B (AI)")).toBe("Version A + mine!");
    expect(changedRemotely(draft, "Version B (AI)")).toBe(true);
    expect(changedRemotely(draft, "Version A")).toBe(false);
  });

  it("shows the server's value without a draft and has nothing to send", () => {
    expect(shownValue(null, "server")).toBe("server");
    expect(changedRemotely(null, "server")).toBe(false);
    expect(hasPendingChange(null)).toBe(false);
    expect(hasPendingChange({ value: "same", original: "same" })).toBe(false);
    expect(hasPendingChange({ value: "new", original: "same" })).toBe(true);
  });
});

describe("storyOf", () => {
  it("names headers, footers and text boxes from their address", () => {
    expect(storyOf("H1")).toEqual({ kind: "header", variant: null });
    expect(storyOf("H2f")).toEqual({ kind: "header", variant: "first" });
    expect(storyOf("F1e")).toEqual({ kind: "footer", variant: "even" });
    expect(storyOf("X3")).toEqual({ kind: "textbox", variant: null });
  });
});
