# fred-capability-spreadsheet

A Fred agent capability (`spreadsheet`, shown as "Generate an Excel file" /
"Générer un fichier Excel") whose tool `create_spreadsheet` turns tabular data
into a downloadable Excel workbook (`.xlsx`).

Design: `openspec/changes/add-spreadsheet-generation/` (issue #3208).

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
- Computed columns: `compute: {op, left, right}` (`add`, `subtract`, `multiply`,
  `divide`) or `{op: "share_of_total", column}`, operands by header name or
  number, optional `round`; each row gets a formula (`=C2*1.2`,
  `=IFERROR(B2/SUM($B$2:$B$4),"")`) and the preview shows the same values.
  A literal column whose values match such a calculation of earlier columns is
  kept, and the success result names the `compute` to use next time.
- Invalid input or a size limit (10 sheets, 50 columns, 5000 rows per sheet,
  50000 cells) returns an error naming the sheet, row and column; no file is
  written, and a limit error asks the model to tell the user and suggest
  splitting. An ambiguous number such as `"1,234"` is refused: numbers travel
  as JSON numbers.
- Formulas: a column `formula` (written for row 2, filled down) and formula cells
  `{"formula": "=..."}`, checked against an allow-list (math, statistics,
  logical, text, date, lookups, `FILTER`/`SORT`/`UNIQUE`) and against the
  workbook's sheets and ranges (`formulas.py`); every formula is evaluated
  server-side (`evaluator.py`, pure Python, cell-read budget) and its value is
  cached in the file. Volatile, network, link and environment functions,
  external workbooks and DDE are refused; plain text starting with `=`, `+`, `-`
  or `@` stays literal, DDE-looking text is refused. No macros.
- Revisions: `changes` (add/remove/edit columns, rows and cells, rename, add or
  remove sheets, move rows) apply to the last delivered request, stored per
  conversation and agent in `cap_spreadsheet_workbook` (`store.py`, own Alembic
  tree `spreadsheet_migrations/`, version table `cap_spreadsheet_alembic_version`);
  existing formulas follow the rows, columns and sheets (`revisions.py`).
- Each call writes a new file and a new card; nothing is overwritten. Revisions
  are named `-v2`, `-v3`, and the chat marks the latest version. Files and
  stored bases are not yet removed when the conversation is erased.
- The file and a JSON preview (first 500 rows per sheet, totals computed for
  display) are written through `RuntimeServices.workspace_fs`; the chat shows a
  `spreadsheet_preview` card that opens a read-only side panel, or a download
  chip when the preview could not be stored. No config or router.

`tools()` only, so it works on ReAct, Deep and Graph agents. Admin-gated: a
platform administrator opens it per team.

## Registration

Installing this package IS the registration: the `fred.capabilities` entry point
points the fred-agents pod at `SpreadsheetCapability`. It is wired into the pod
as an editable path dependency of `apps/fred-agents`.

## Dev

```
make code-quality   # ruff + format + bandit + detect-secrets + type-check
make test           # offline unit tests
```
