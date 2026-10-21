# fred-capability-spreadsheet

A Fred agent capability (`spreadsheet`) whose tool `create_spreadsheet` turns
tabular data into a downloadable Excel workbook (`.xlsx`).

Design: `openspec/changes/add-spreadsheet-generation/` (issue #3208).

## What it ships

- **Tool** `create_spreadsheet(file_name, sheets)`: sheets with typed columns
  (text, number, integer, percent, currency with an optional symbol, date), a
  bold frozen header, an auto filter, column widths and an optional totals row
  written as Excel formulas.
- Invalid input or a size limit (10 sheets, 50 columns, 5000 rows per sheet,
  50000 cells) returns an error naming the sheet, row and column; no file is written.
- Text that looks like a formula is stored as literal text. No macros.
- The file is written through `RuntimeServices.workspace_fs` and shown in the
  chat as a download chip. No config, table, router or chat part.

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
