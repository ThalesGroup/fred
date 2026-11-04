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

// Pure helpers of the "Rédaction" view. The backend view
// (`GET /sessions/{id}/content`, see content.py) hands out every address
// and every structural operation ready-made; these helpers only complete the
// text of an edit (`text` / `markdown` / `find`+`replace`) and never build an
// address. All types come from the generated client.

import type {
  CellView,
  ContentOperation,
  Place,
  TableBlock,
  TextSegment,
  WordTemplateEditRequest,
} from "./api/wordTemplateCapabilityOpenApi";

// --- set_text: inline Markdown -------------------------------------------------

const INLINE_SPECIAL_RE = /([\\`*_])/g;
const INLINE_ESCAPE_RE = /\\([\\`*_])/g;
// A marker NOT preceded by a backslash escape (the backend escapes every
// literal one, so an unescaped marker means formatting: bold, italic, code).
const UNESCAPED_MARKER_RE = /(^|[^\\])(\\\\)*[`*_]/;

/** Escape the literal `\ * _ \`` characters of plain text for `set_text`. */
export function escapeInlineMarkdown(text: string): string {
  return text.replace(INLINE_SPECIAL_RE, "\\$1");
}

/** Undo `escapeInlineMarkdown`. */
export function unescapeInlineMarkdown(markdown: string): string {
  return markdown.replace(INLINE_ESCAPE_RE, "$1");
}

/**
 * How a `set_text` place is edited. A place without formatting is edited as
 * plain text (escaped on save) so the collaborator never sees a backslash; a
 * place with bold/italic/code keeps its Markdown so saving does not drop it.
 */
export type InlineEditMode = "plain" | "markdown";

export interface InlineEditable {
  mode: InlineEditMode;
  value: string;
}

export function inlineEditable(place: Pick<Place, "markdown" | "text">): InlineEditable {
  const markdown = place.markdown ?? escapeInlineMarkdown(place.text ?? "");
  if (UNESCAPED_MARKER_RE.test(markdown)) return { mode: "markdown", value: markdown };
  return { mode: "plain", value: unescapeInlineMarkdown(markdown) };
}

/** The `set_text` operation for a place, from the value typed in `mode`. */
export function setTextOperation(address: string, value: string, mode: InlineEditMode): ContentOperation {
  return { op: "set_text", address, text: mode === "plain" ? escapeInlineMarkdown(value) : value };
}

// --- replace_text: a place holding a field --------------------------------------

/** Whether a piece of a `replace_text` place can be edited (fields and blank pieces cannot). */
export function isEditablePiece(piece: { text: string; field?: boolean }): boolean {
  return !piece.field && piece.text.trim().length > 0;
}

/**
 * One `replace_text` per changed piece. `values` holds the typed value of
 * each piece, by index (missing = unchanged). `find` is the piece's current
 * text - plain text, no escaping.
 */
export function replaceTextOperations(place: Place, values: Record<number, string>): ContentOperation[] {
  const out: ContentOperation[] = [];
  (place.pieces ?? []).forEach((piece, index) => {
    const value = values[index];
    if (value === undefined || value === piece.text || !isEditablePiece(piece)) return;
    out.push({ op: "replace_text", address: place.address, find: piece.text, replace: value });
  });
  return out;
}

// --- write: rich text -------------------------------------------------------------

/** MDXEditor's output, made fit for `write`: no trailing blank lines, no `&#x20;` space entities. */
export function normalizeEditorMarkdown(markdown: string): string {
  return markdown
    .replace(/&#x20;/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+$/, "");
}

/** A text segment's ready-made edit (`write` over its range, or `insert_after` its heading) with the new Markdown. */
export function segmentOperation(segment: Pick<TextSegment, "edit">, markdown: string): ContentOperation {
  return { ...segment.edit, markdown: normalizeEditorMarkdown(markdown) };
}

/** A multi-paragraph cell's `write`. */
export function cellWriteOperation(address: string, markdown: string): ContentOperation {
  return { op: "write", from: address, markdown: normalizeEditorMarkdown(markdown) };
}

/** The request body of `POST /edits`: the batch is made on the view's `seq`. */
export function editRequest(seq: number, operations: ContentOperation[]): WordTemplateEditRequest {
  return { base_seq: seq, operations };
}

// --- tables -------------------------------------------------------------------------

export type TableSlot = { kind: "cell"; cell: CellView } | { kind: "gap"; span: number };

/**
 * The rows of a table as HTML table slots: merged cells keep their
 * `col_span`/`row_span` (continuation cells of a vertical merge are absent
 * from the view), and grid columns no cell covers (a row starting late, a
 * short row) become empty gap slots so the columns stay aligned.
 */
export function tableLayout(table: Pick<TableBlock, "rows" | "n_cols">): TableSlot[][] {
  const rows = table.rows ?? [];
  const width = Math.max(
    table.n_cols,
    ...rows.map((row) =>
      Math.max(0, ...(row.cells ?? []).map((cell) => cell.col - 1 + Math.max(1, cell.col_span ?? 1))),
    ),
  );
  // Columns still covered by a cell of a row above (vertical merges): column -> rows left.
  const coveredBelow = new Map<number, number>();
  return rows.map((row) => {
    const covered = new Set<number>();
    for (const [col, left] of coveredBelow) {
      covered.add(col);
      if (left <= 1) coveredBelow.delete(col);
      else coveredBelow.set(col, left - 1);
    }
    const startAt = new Map((row.cells ?? []).map((cell) => [cell.col, cell]));
    const slots: TableSlot[] = [];
    let col = 1;
    while (col <= width) {
      if (covered.has(col)) {
        col += 1;
        continue;
      }
      const cell = startAt.get(col);
      if (cell) {
        const colSpan = Math.max(1, cell.col_span ?? 1);
        const rowSpan = Math.max(1, cell.row_span ?? 1);
        slots.push({ kind: "cell", cell });
        if (rowSpan > 1) for (let c = col; c < col + colSpan; c += 1) coveredBelow.set(c, rowSpan - 1);
        col += colSpan;
        continue;
      }
      const last = slots[slots.length - 1];
      if (last?.kind === "gap") last.span += 1;
      else slots.push({ kind: "gap", span: 1 });
      col += 1;
    }
    return slots;
  });
}

// --- headers, footers, text boxes ------------------------------------------------------

export type StoryKind = "header" | "footer" | "textbox";
export type StoryVariant = "first" | "even" | null;

/**
 * What a `fields` block is, from its story address: `H1`/`F1` (default),
 * `H1f`/`F1f` (first page), `H1e`/`F1e` (even pages), `X...` a text box. The
 * backend's `label` is a technical English string; the UI words it itself.
 */
export function storyOf(address: string): { kind: StoryKind; variant: StoryVariant } {
  const match = /^([HF])\d+([fe]?)$/.exec(address);
  if (!match) return { kind: "textbox", variant: null };
  return {
    kind: match[1] === "H" ? "header" : "footer",
    variant: match[2] === "f" ? "first" : match[2] === "e" ? "even" : null,
  };
}

// --- errors of POST /edits and /undo ------------------------------------------------

export type EditFailure =
  | { kind: "stale"; seq: number }
  | { kind: "rejected"; message: string; problems: string[] }
  | { kind: "other"; message: string };

/**
 * Classify an RTK Query error of an edit: a 409 carrying `seq` = the document
 * changed since the view (reload), 422 = the batch was rejected
 * (`detail.problems`); another 409 (the document cannot be built) is a failure.
 */
export function classifyEditError(error: unknown): EditFailure {
  const err = (error ?? {}) as { status?: unknown; data?: unknown; error?: unknown };
  const detail = (err.data as { detail?: unknown } | undefined)?.detail;
  const asObject = detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
  const message =
    typeof asObject?.message === "string"
      ? asObject.message
      : typeof detail === "string"
        ? detail
        : typeof err.error === "string"
          ? err.error
          : `HTTP ${String(err.status ?? "?")}`;
  if (err.status === 409 && typeof asObject?.seq === "number") {
    return { kind: "stale", seq: asObject.seq };
  }
  if (err.status === 422) {
    const problems = Array.isArray(asObject?.problems)
      ? asObject.problems.filter((p): p is string => typeof p === "string")
      : Array.isArray(detail)
        ? detail.map((d) => String((d as { msg?: unknown })?.msg ?? d))
        : [];
    return { kind: "rejected", message, problems };
  }
  return { kind: "other", message };
}

// --- local drafts vs. the AI's edits --------------------------------------------------

/**
 * What the collaborator typed in one place, and the server value it started
 * from. Kept across view refreshes (the AI editing meanwhile) so a refresh
 * never clobbers the field being edited.
 */
export interface PlaceDraft {
  value: string;
  original: string;
}

/** Start (or continue) a draft when the collaborator types. */
export function typeInDraft(draft: PlaceDraft | null, serverValue: string, value: string): PlaceDraft {
  return { value, original: draft?.original ?? serverValue };
}

/** The value the field shows: the draft while there is one, else the server's. */
export function shownValue(draft: PlaceDraft | null, serverValue: string): string {
  return draft ? draft.value : serverValue;
}

/** Whether the server changed this same place while the collaborator was editing it. */
export function changedRemotely(draft: PlaceDraft | null, serverValue: string): boolean {
  return draft !== null && serverValue !== draft.original;
}

/** Whether a draft has something to send (typed text that differs from where it started). */
export function hasPendingChange(draft: PlaceDraft | null): draft is PlaceDraft {
  return draft !== null && draft.value !== draft.original;
}
