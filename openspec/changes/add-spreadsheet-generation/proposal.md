## Why

Fred agents read Excel files but cannot write one: asked for a spreadsheet, an agent pastes a Markdown table the user reformats by hand. Users then ask for targeted changes ("add a column", "split into two sheets") and for real formulas (lookups, a summary sheet). GitHub issue #3208.

## What Changes

- **New capability `spreadsheet`** ("Generate an Excel file" / "Générer un fichier Excel"), one tool `create_spreadsheet`, tool-only so it runs on ReAct, Deep and Graph agents; admin-gated; a pack in the agent form's Document production section.
- **`.xlsx` generation** with XlsxWriter: typed columns, currency symbols, frozen styled header, auto filter, widths, an optional totals row of live formulas labelled in the conversation language.
- **Formulas**: a column `formula` (filled down) and formula cells, over an allow-list of functions, cross-sheet references checked; every formula evaluated server-side and cached in the file.
- **Targeted revisions**: `changes` applied to the last workbook delivered in the conversation, stored in a capability-owned table; each delivery is a new versioned file (`Budget-v2.xlsx`).
- **Validation returned to the model** (`is_error`, nothing written) and success-text notes for likely mistakes (manual total rows, literal derived columns).
- **In-chat preview**: a card and a read-only Excel-like side panel fed by a JSON preview stored beside the file.
- **Safety**: `.xlsx` only, no macros; formulas only from the explicit forms; DDE and external-workbook patterns refused even as text.

## Capabilities

### New Capabilities

- `spreadsheet-generation`: generating and revising a downloadable Excel workbook from a chat request.

### Modified Capabilities

- none.

## Impact

- New package `libs/capabilities/fred-capability-spreadsheet/` (runtime dependency `xlsxwriter`, already in the image through python-pptx; `openpyxl` for tests only), wired into `apps/fred-agents` and the repo lists like the other capability packages.
- New table `cap_spreadsheet_workbook` with its own Alembic tree (`spreadsheet_migrations/`, one revision), applied by `python -m fred_runtime migrate`. Migration note `impact: minor`.
- Frontend plugin `features/capabilities/spreadsheet/`, one pack in `toolPacks.ts`, en/fr strings, Help Center section. No new endpoint: the preview is read through `/fs/download`.
- No SDK, runtime, control-plane or OpenAPI change.

## Out of scope

Roadmap in #3215: charts, conditional formatting, templates, revising an uploaded or user-edited file, functions outside the allow-list. Generated files survive conversation erasure (#3212).
