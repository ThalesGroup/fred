## Decisions

### D1. Own package, tool only

`fred-capability-spreadsheet`, one tool `create_spreadsheet`, no middleware, so it runs on ReAct, Deep and Graph agents. Admin-gated like the other output capabilities. Files go through the existing `RuntimeServices.workspace_fs` port; no router.

Rejected: extending `writable_document` (co-edited Markdown lifecycle), `fred-capability-documents` (Knowledge Flow readers) or the PPT package (python-pptx and LibreOffice coupling).

### D2. Schema kept small for Mistral models

`create_spreadsheet(file_name, sheets | changes, language?)`. A column has `header`, `type` (`text`, `number`, `integer`, `percent`, `currency`, `date`), `currency`, `width`, `total` (`sum`, `average`, `min`, `max`, `count`) and `formula`. Scalar cells; dates as ISO strings; enums case-insensitive; unknown keys ignored. `language` is an argument because the capability context does not carry the turn language (an SDK change for one label was not worth it).

### D3. Generation

XlsxWriter in a worker thread, at most 4 builds per pod (fail fast, as PPT Filler). Values are validated and converted once (`prepare`); the writer and the preview read the same result. Dates use Excel's built-in short-date format, so they follow the reader's locale. The totals label names the functions used in the conversation language.

XlsxWriter over openpyxl: it writes cached formula values and dynamic-array metadata, and is already in the image.

### D4. Validation and limits

Every malformed input returns `is_error` naming sheet, row and column, and no file is written. Limits: 10 sheets, 50 columns, 5 000 rows per sheet, 50 000 cells, 2 000 characters per cell, 10 MB. Never truncate silently: a limit error tells the model to inform the user and suggest splitting.

### D5. Formulas only in explicit forms

A column `formula` (the first data row's formula, filled down like Excel) and a formula cell `{"formula": "..."}`. A plain string that parses as a formula is refused with the exact formula-cell form; other text starting with `=`, `+`, `-`, `@` is written as literal text. Text holding a DDE or external-workbook pattern is refused even as text, since a CSV re-export would make it live.

Fill-down: a range without `$` is anchored (every row reads the whole table), except a range on the formula's own row (`=SUM(B2:D2)`), which shifts. A formula cell in a formula column overrides it.

### D6. Allow-list and references

English function names and commas; a French name is refused with the English form. The allow-list covers math, statistics, conditional aggregates, finance, logical, text, date (`TODAY`/`NOW` frozen at build time), lookups (`XLOOKUP`, `FILTER`, `SORT`, `UNIQUE`, `SEQUENCE`) and `LET`; the writer emits Excel's `_xlfn.` prefixes and spill metadata. Refused: volatile (`INDIRECT`, `OFFSET`, `RAND*`), network or link (`WEBSERVICE`, `HYPERLINK`, ...), environment (`CELL`, `INFO`), XLM, external workbooks, DDE, defined names, structured and whole-column references, R1C1. A function is allowed only if the evaluator implements it. No `LAMBDA`.

Cross-sheet references must name a sheet of the workbook and stay inside its data and totals rows; a range may not span both.

### D7. Own evaluator, cached values

A pure-Python tokenizer, parser and evaluator over the allow-list, with Excel semantics, evaluates every formula; values are cached in the file and shown in the preview, so viewers that do not recalculate show numbers. The workbook still recalculates on open. A cell-read budget stops pathological requests.

Rejected: `formulas` (EUPL, numpy/scipy), `pycel` (GPL), `xlcalculator` (unmaintained, no `XLOOKUP`), LibreOffice recalculation (no `XLOOKUP`/`FILTER` in the image's version, 1 to 3 s per call).

### D8. Derived columns use `formula`; `compute` removed

A structured `compute` (add, subtract, ... by header name) shipped first, then was removed: in the A/B bench, formula-only creation scored higher on both models and the schema shrank (8 406 to 6 720 characters). Totals stay on `total`; a sheet-level `total` map that models send is applied to the named columns or refused with the fix, never dropped.

### D9. Notes, not refusals, for likely mistakes

After a successful build, the success text may name a literal column that looks derived (with the formula to set), a manual total row next to the automatic one, a trailing stat row ("Moyenne ...") included in a total, or an `average` total on a percent column. These can be intended, so the file is kept. With a note, the success text invites a fix through `changes` instead of "do not create it again".

### D10. Revisions apply to the stored request

`changes` (add/remove/edit column, add/remove/edit rows, edit cell, add/rename/remove sheet, move rows) are resolved on the base's names and numbers, applied as one step, and the whole resulting request goes through the normal build. Formula references follow structural changes like Excel; a change that would break a formula is refused, naming it. All errors are listed at once.

Rejected: rebuilding the base from conversation history (trimmed), patching the stored `.xlsx` (a second write path), a read tool (an extra round per revision).

### D11. Base in a capability-owned table

`cap_spreadsheet_workbook`, key `(session_id, agent_instance_id)`, own Alembic tree with one initial revision, version table `cap_spreadsheet_alembic_version`. One upsert per delivery; replica-safe. Bases over 4 MB are not stored and the success text says so.

Rejected: a control-plane table (capability boundary), the conversation filesystem (optional and agent-editable), a spec file in workspace storage (the port is write-only).

### D12. Versions and duplicate calls

A `changes` call, or `sheets` with the base's file name, makes the next version (`Budget-v2.xlsx`); every version is a new file and card, and the chat marks the latest. An identical call repeated in the same turn returns the first result without a new file.

### D13. In-chat preview

A JSON preview (first 500 rows, evaluated values, one formula template per formula column) is written beside the file; a `spreadsheet_preview` card opens a read-only Excel-like side panel. If the preview cannot be stored, the plain download chip is shown and the file is still delivered.

## Known limitations

- Only the last delivered workbook can be revised; bases and generated files are never deleted (#3212, #2990).
- The evaluator follows Excel for the allow-list; rare edge cases may differ in the preview and in viewers that do not recalculate.
- A `SUM($B$2:B2)` running total over thousands of rows exceeds the evaluation budget (use `=C1+B2`).
- Follow-ups: #3212 erasure, #3213 `#`/`%` in file names, #3214 card auto-open heuristic, #3215 roadmap.
