## Why

Fred agents read Excel files through the tabular tools but cannot write one. Asked for a spreadsheet, an agent pastes a Markdown table that the user copies into Excel and reformats by hand. The agent form's Document production section offers Word, PowerPoint and web page outputs, and nothing for spreadsheets. GitHub issue #3208.

Extension (owner, 2026-10-28), in the same PR #3220: once a file exists, a user asks for targeted changes ("ajoute une colonne", "ajoute une ligne avec ces valeurs", "sépare ce tableau en 2 onglets"), and today the model must resend the whole workbook, which costs tokens and lets a weak model reword or drop rows nobody asked to touch. Users also expect real Excel formulas (lookups, conditional sums, a summary sheet reading the other sheets), which the structured `compute`/`total` paths cannot express. Review of the PR also found that sheet-qualified, external-workbook and DDE formulas slip past the formula guard as literal text, and that generated formulas carry no cached value, so viewers that do not recalculate show blanks.

## What Changes

- **New capability `spreadsheet`** with one tool, `create_spreadsheet`. Users see it as "Generate an Excel file" / "Générer un fichier Excel", like its neighbours ("Générer un document Word", "Générer une page web").
- **`.xlsx` generation with XlsxWriter** (replaces openpyxl at runtime, D15; already in the fred-agents image through python-pptx; openpyxl stays a test dependency to read files back): one or more sheets, typed columns (text, number, integer, percent, currency, date), a per-column currency (`EUR`, `USD`, ...) shown as a symbol in the number format, styled and frozen header row, auto filter, column widths (declared or computed), an optional totals row whose cells are live Excel formulas (`SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`) and whose label names those functions in the conversation language (optional `language` argument, `fr` by default). Dates use Excel's built-in short-date format, which follows the reader's system locale.
- **Computed columns** (owner decision 2026-10-21): a column may declare `compute` from other columns by header name (`add`, `subtract`, `multiply`, `divide`, `share_of_total`, optional `round`); the file holds a real formula on every row (`=C2*1.2`, `=IFERROR(B2/SUM($B$2:$B$N),"")`) and the preview shows the same values computed server-side.
- **Delivery through the existing output port**: the file is written with `RuntimeServices.workspace_fs`. No router or table.
- **In-chat preview** (owner decision 2026-10-21, option A): a compact JSON preview is stored beside the file; a `spreadsheet_preview` chat part (card with Preview and download) opens a read-only `spreadsheet_pane` side panel through the existing capability plugin mechanism (like PPT Filler's deck preview). Falls back to the standard `LinkPart` download chip when the preview cannot be stored.
- **Validation returned to the model**: wrong or reserved sheet name, row length mismatch, unparsable, ambiguous (`"1,234"`) or non-finite value for a column type, an over-long header, or a size limit returns an `is_error` tool result naming the sheet, row and column, and no file is written. A limit error tells the model to inform the user plainly and suggest splitting. Control characters are stripped from cells and headers.
- **Targeted revisions** (D10-D12): `create_spreadsheet` takes `sheets` (the whole workbook) **or** `changes` applied to the last workbook delivered in the conversation: add/remove/edit a column (computed included), add/remove/edit rows, edit a cell, rename/add/remove a sheet, move rows to a new or existing sheet. The base is stored per conversation and agent in a capability-owned table, so a revision survives history trimming and works on Graph agents. Each delivery is a new file and card, named `Budget.xlsx`, `Budget-v2.xlsx`, `Budget-v3.xlsx`; the chat marks the latest version.
- **Formulas and cross-sheet references** (D13-D16): a column `formula` (written for the first data row, filled down like Excel) and a formula cell `{"formula": "..."}` accept real Excel formulas over an allow-list of functions (math, statistics, logical, text, date, lookups including `XLOOKUP` and `FILTER`, written with their `_xlfn.`/`_xlws.` prefixes); references to other sheets (`='Données 2025'!B2`, `Synthèse!B2:B10`) are checked against the workbook's sheets, columns and rows. Volatile and dangerous functions, external workbooks and DDE are refused. `compute` and `total` stay the simple route and compile to the same formulas.
- **Cached values** (D15): every formula is evaluated server-side by a small pure-Python evaluator covering exactly the allow-list; the value is written in the file beside the formula and shown in the preview, so a viewer that does not recalculate shows the right numbers.
- **Safety**: no macros (`.xlsx` only); formulas only from `compute`, `total`, column `formula` and formula cells, each validated against the allow-list; plain text cells starting with `=`, `+`, `-`, `@` stay literal text, and a text cell holding a DDE or external-workbook pattern (`=cmd|' /C calc'!A0`, `=[x.xlsx]Feuil1!A1`) is refused outright.
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
- Extension: capability-owned table `cap_spreadsheet_workbook` with its own Alembic tree (`spreadsheet_migrations/`, version table `cap_spreadsheet_alembic_version`, `migrations_location()`), applied by `python -m fred_runtime migrate`; row in `docs/swift/ops/DATABASE_MIGRATIONS.md`. Runtime dependency `xlsxwriter` replaces `openpyxl` (moved to test dependencies); `fred-agents` `uv.lock` loses `openpyxl` and `et-xmlfile`. The `spreadsheet_preview` part gains `workbook_id` and `version` (capability-owned type in `features/capabilities/spreadsheet/types.ts`, not a generated client).
- No SDK, runtime, control-plane or OpenAPI change, so no frozen contract entry. No stored-config migration (`ConfigModel = EmptyModel`).
- Migration note per `docs/swift/ops/MIGRATION-GUIDES.md`: `impact` becomes `minor` with the new Alembic revision (applied by the standard fred-agents migration hook; no configuration change).
- Known limitation: erasing a conversation does not delete its generated `.xlsx` and `.preview.json` (same as PPT Filler outputs), tracked in #3212.

## Out of scope / later

Ranked roadmap in #3215; none of this is in this change:

- Modifying a file the user edited and uploaded, or a workbook other than the last one delivered (revisions apply to the stored spec of the last delivery, D10).
- Reusing a generated file as tabular input.
- Retention, cleanup and quotas for generated files (erasure cascade: #3212).
- Functions outside the allow-list (D14), defined names, structured table references, whole-column references, external links; see design.md "Deferred gaps".
- Advanced formatting: charts, conditional formatting, merged cells, several tables per sheet, hyperlinks, comments, data validation.
- Transforming an uploaded CSV/Excel into a workbook.
- Large SQL exports written server-side (#2738).
- Dedicated KPIs or audit events.
- A mobile-specific pane layout.
- Corporate templates.
