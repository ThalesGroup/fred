# fred-capability-spreadsheet

A Fred agent capability (`spreadsheet`, shown as "Generate an Excel file" /
"Générer un fichier Excel") whose tool `create_spreadsheet` turns tabular data
into a downloadable Excel workbook (`.xlsx`).

## What it ships

- **Tool** `create_spreadsheet(file_name?, sheets | changes, language?)`: sheets with typed
  columns (text, number, integer, percent, currency with an optional symbol,
  date in Excel's built-in short-date format, which follows the reader's locale),
  a bold frozen header, an auto filter, column widths and an optional totals row
  written as Excel formulas. Its label names the functions in the conversation
  language (`language`, `fr` by default): Total, Moyenne/Average, Min, Max,
  Nombre/Count.
  A data row labelled like a total ("Total", "Sous-total"...) that repeats
  or leaves empty the totals is kept, and the success result names it.
- Derived columns use a column `formula` (row 2, filled down). A literal column
  whose values match a difference, ratio or share of total of earlier columns is
  kept, and the success result names the `formula` to use next time.
- Invalid input or a size limit (10 sheets, 50 columns, 5000 rows per sheet,
  50000 cells) returns an error naming the sheet, row and column; no file is
  written, and a limit error asks the model to tell the user and suggest
  splitting. An ambiguous number such as `"1,234"` is refused: numbers travel
  as JSON numbers.
- Formulas: a column `formula` (written for row 2, filled down) and formula cells
  `{"formula": "=..."}`, checked against an allow-list (math, statistics,
  finance, logical, information, text, date, lookups, `LET`, dynamic arrays
  `FILTER`/`SORT`/`UNIQUE`/`SEQUENCE`) and against the
  workbook's sheets and ranges (`formulas.py`); every formula is evaluated
  server-side (`evaluator.py`, pure Python, cell-read budget) and its value is
  cached in the file (`TODAY`/`NOW` with one build time, reported in the
  preview and the success text). `RAND*`, `INDIRECT`/`OFFSET`, network, link and environment functions,
  external workbooks and DDE are refused; plain text starting with `=`, `+`, `-`
  or `@` stays literal, DDE-looking text is refused. No macros.
- Revisions use `changes` with the source `document_id` and `expected_content_id`
  returned by the tool. The user still asks naturally, for example "add a row";
  the agent selects the requested file. Missing references return candidates from
  the 20 newest conversation outputs, never an implicit "last workbook".
  Formulas follow rows, columns and sheets through the existing revision engine.
- The XLSX carries its validated specification, business name, lineage UUID and
  version in a standard custom XML part (`customXml/fred-spreadsheet.xml`). A
  canonical SHA-256 of the other ZIP members detects external edits, including
  edits that preserve the custom XML. This is consistency validation, not authority.
  External edits require a new full specification; arbitrary XLSX import is not
  supported. Sources are bounded to 32 MiB compressed, 64 MiB uncompressed,
  256 ZIP entries and 4 MiB of embedded JSON; encrypted and duplicate members
  are refused. Work exceeding a limit fails without silently discarding data.
- Control Plane's conversation catalogue owns files, authorization, publication
  and erasure. No spreadsheet table, migration, stored "latest" pointer or rollback
  protocol remains. A revision reads one bounded, conversation-scoped snapshot
  and rejects a different content identity before decoding or building. Later
  source edits/deletion do not invalidate the copied snapshot; conversation closure
  still fences publication through Control Plane.
- Creation uses a unique output path. The immutable source content selects a
  deterministic successor path, retaining its business filename with `-v2`, `-v3`,
  etc. `expected_content_id=None` requires an empty destination: concurrent calls
  cannot publish two active successors or silently rebase. Deleting a successor
  permits deriving its source again. Renaming a revision requires a new workbook.
- JSON preview data (first 500 rows per sheet) uses the existing preview content
  kind, tied to that exact XLSX content on the same path. It is not a second
  visible file. The chat part carries `document_id`, `content_id`, `workbook_id`
  and `version`; the model receives source references even if preview publication
  fails and the UI falls back to a download chip. Generic PDF viewers and wiki
  copies select only PDF previews, leaving the spreadsheet JSON to its own pane.
- Up to four source reads/builds run per pod. Blocking validation, archive handling
  and calculation stay in worker threads; cancellation holds each worker's slot
  until it actually ends. Typed authority failures and graph interruptions propagate.

`tools()` works on ReAct, Deep and Graph agents. Capability availability follows
Weaver agent configuration and the registered capability manifest.

## Registration

Installing this package IS the registration: the `fred.capabilities` entry point
points the fred-agents pod at `SpreadsheetCapability`. It is wired into the pod
as an editable path dependency of `apps/fred-agents`.

## Dev

```
make code-quality   # ruff + format + bandit + detect-secrets + type-check
make test           # offline unit tests
```
