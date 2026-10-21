## Why

Fred agents read Excel files through the tabular tools but cannot write one. Asked for a spreadsheet, an agent pastes a Markdown table that the user copies into Excel and reformats by hand. The agent form's Document production section offers Word, PowerPoint and web page outputs, and nothing for spreadsheets. GitHub issue #3208.

## What Changes

- **New capability `spreadsheet`** with one tool, `create_spreadsheet`. Users see it as "Generate an Excel file" / "Générer un fichier Excel", like its neighbours ("Générer un document Word", "Générer une page web").
- **`.xlsx` generation with openpyxl** (bytes are not deterministic: openpyxl stamps times): one or more sheets, typed columns (text, number, integer, percent, currency, date), a per-column currency (`EUR`, `USD`, ...) shown as a symbol in the number format, styled and frozen header row, auto filter, column widths (declared or computed), an optional totals row whose cells are live Excel formulas (`SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`) and whose label names those functions in the conversation language (optional `language` argument, `fr` by default). Dates use Excel's built-in short-date format, which follows the reader's system locale.
- **Computed columns** (owner decision 2026-10-21): a column may declare `compute` from other columns by header name (`add`, `subtract`, `multiply`, `divide`, `share_of_total`, optional `round`); the file holds a real formula on every row (`=C2*1.2`, `=IFERROR(B2/SUM($B$2:$B$N),"")`) and the preview shows the same values computed server-side.
- **Delivery through the existing output port**: the file is written with `RuntimeServices.workspace_fs`. No router or table.
- **In-chat preview** (owner decision 2026-10-21, option A): a compact JSON preview is stored beside the file; a `spreadsheet_preview` chat part (card with Preview and download) opens a read-only `spreadsheet_pane` side panel through the existing capability plugin mechanism (like PPT Filler's deck preview). Falls back to the standard `LinkPart` download chip when the preview cannot be stored.
- **Validation returned to the model**: wrong or reserved sheet name, row length mismatch, unparsable, ambiguous (`"1,234"`) or non-finite value for a column type, an over-long header, or a size limit returns an `is_error` tool result naming the sheet, row and column, and no file is written. A limit error tells the model to inform the user plainly and suggest splitting. Control characters are stripped from cells and headers.
- **Each request writes a new file and a new card**; nothing is overwritten.
- **Safety**: no macros (`.xlsx` only), no free-form formulas (only generated totals and computed-column formulas using `SUM`, `ROUND`, `IFERROR` on the same sheet), and text cells starting with `=`, `+`, `-`, `@` are stored as literal text.
- **Tool-only capability** (`tools()`, default `execution_models`), so it works on ReAct, Deep and Graph agents. The tool schema stays simple for Mistral models.
- **Agent form**: a "Generate an Excel file" pack in the Document production section; en/fr labels. Admin-gated like the other output capabilities.
- **Help Center**: a "Generate an Excel file" section in `features/capabilities.md`, en and fr.

## Capabilities

### New Capabilities

- `spreadsheet-generation`: generating a downloadable Excel workbook from a chat request.

### Modified Capabilities

- none. `agent-capability-packs` does not enumerate the Document production packs, so adding one needs no delta; the form requirement lives in `spreadsheet-generation`.

## Impact

- New package `libs/capabilities/fred-capability-spreadsheet/` (entry point `spreadsheet`), dependency `openpyxl>=3.1.5` (Knowledge Flow pins 3.1.5).
- `apps/fred-agents/pyproject.toml` + `uv.lock`: the new package as an editable path dependency; image, pyright, pre-commit, CI change detection and root Makefile lists gain the package like the other capability packages.
- `apps/frontend/src/rework/features/capabilities/spreadsheet/` (plugin, card, pane, slice registered in `common/store.tsx`, plugin listed in `capabilities/index.ts`); no new endpoint, the preview is read through the existing `/fs/download` route.
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/toolPacks.ts`: one pack; `apps/frontend/src/locales/{en,fr}/translation.json`: capability and pack strings.
- `apps/frontend/src/rework/features/helpCenter/content/{en,fr}/features/capabilities.md`.
- `docs/swift/capabilities/AUTHORING.md`: one row; package `README.md`.
- No SDK, runtime, control-plane or OpenAPI change. No stored-config migration (`ConfigModel = EmptyModel`).
- Migration note per `docs/swift/ops/MIGRATION-GUIDES.md`.
- Known limitation: erasing a conversation does not delete its generated `.xlsx` and `.preview.json` (same as PPT Filler outputs), tracked in #3212.

## Out of scope / later

Ranked roadmap in #3215; none of this is in this change:

- Modifying an existing file (no workspace read-back; each change writes a new file).
- Reusing a generated file as tabular input.
- Retention, cleanup and quotas for generated files (erasure cascade: #3212).
- Formulas beyond the computed-column ops (other functions, cross-sheet references, lookups); per-row formulas for add, subtract, multiply, divide and share of total are in this change.
- Advanced formatting: charts, conditional formatting, merged cells, several tables per sheet, hyperlinks, comments, data validation.
- Transforming an uploaded CSV/Excel into a workbook.
- Large SQL exports written server-side (#2738).
- Dedicated KPIs or audit events.
- A mobile-specific pane layout.
- Corporate templates.
