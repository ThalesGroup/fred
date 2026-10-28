Tracking: GitHub issue #3208. Paths relative to the repository root.

## 1. Package and capability

- [x] 1.1 Scaffold `libs/capabilities/fred-capability-spreadsheet/` from `fred-capability-html-artifact` (pyproject with `openpyxl>=3.1.5`, entry point `spreadsheet`, Makefile, baselines, `uv.lock`, README)
- [x] 1.2 `SpreadsheetCapability`: manifest (`id="spreadsheet"`, i18n name/description, `icon`), `ConfigModel = EmptyModel`, `tools()` returning `create_spreadsheet`; default `execution_models` and `team_scope`
- [x] 1.3 Tool input models (D2) with case-insensitive enums and the per-column currency
- [x] 1.4 Workbook builder (D3) in a worker thread: types to number formats, currency symbols, header style, freeze, auto filter, widths, totals formulas
- [x] 1.5 Validation and limits (D4) with messages naming sheet / row / column; formula-injection guard (D5)
- [x] 1.6 Delivery through `workspace_fs` and `LinkPart` (D6); `is_error` when the port is absent
- [x] 1.7 Wire into `apps/fred-agents` (pyproject, `uv.lock`, image, shipped-ids boot test) and the repo lists (root Makefile, pre-commit, CI change detection, release order); `registry.validate()` passes at boot

## 2. Frontend

- [x] 2.1 `toolPacks.ts`: `CAP_SPREADSHEET` and a pack in `document_production`
- [x] 2.2 `locales/{en,fr}/translation.json`: `capability.spreadsheet.name/description`, pack title/description
- [x] 2.3 Pack logic tests updated (toolPackLogic) if they enumerate packs

## 3. Help Center

- [x] 3.1 "Generate an Excel file" section under Document production in `helpCenter/content/en/features/capabilities.md` (what it does, limits, example)
- [x] 3.2 Same section in `fr/features/capabilities.md` ("Générer un fichier Excel")

## 3b. In-chat preview (option A, 2026-10-21)

- [x] 3b.1 `build_preview` (D8): typed values, display decimals, 500-row cap with `row_count`, computed totals; written as `<file>.preview.json`; `spreadsheet_preview` part + `spreadsheet_pane` in the manifest; `LinkPart` fallback on build or upload failure
- [x] 3b.2 Frontend plugin `capabilities/spreadsheet/`: card (Preview + download), slice in `common/store.tsx`, lazy `SpreadsheetPane` (sheet tabs, sticky header row and first column, locale formats, totals row, truncation note, unavailable state), en/fr strings
- [x] 3b.3 Help Center en/fr: preview paragraph in "Generate an Excel file"; AUTHORING row, README, migration note updated
- [x] 3b.4 Tests: preview JSON (formats, totals, empty column, cap, sheets), capability (preview written, part fields, both fallbacks); vitest `SpreadsheetPane` and `spreadsheetFormat`
- [x] 3b.5 Excel-like pane (owner request 2026-10-21): column letters, row numbers, workbook header as row 1, one scroll area with frozen headings, bottom sheet tabs with overflow arrows, name box; vitest updated

## 4. Tests and verification

- [x] 4.1 Offline tests: workbook read back with openpyxl (sheets, headers, values, number formats, currency symbols, freeze, widths, totals formulas), every validation error, every limit, injection guard, missing port
- [x] 4.2 Capability tests: manifest, entry point discovery, tool schema has only LLM arguments, Graph assembly accepts it
- [x] 4.3 `make code-quality`, `make test` in the package, fred-agents and frontend; `ruff --select I` and basedpyright
- [ ] 4.4 Live check on the default Mistral model, a ReAct agent and a Deep agent delegating to a sub-agent: request -> tool call -> download -> file opens in LibreOffice without repair; record in verification evidence
- [x] 4.5 `fred-performance-reviewer` on the tool call site (CPU work off the event loop)

## 4b. Review fixes and owner decisions (2026-10-21)

- [x] 4b.1 Control characters stripped from cells and headers, rejected in sheet names; `History` reserved; header length bounded like cells
- [x] 4b.2 Ambiguous `"1,234"` and NaN/Infinity refused; description asks for JSON numbers
- [x] 4b.3 `#` and `%` stripped from file names (stopgap, #3213)
- [x] 4b.4 Values converted once (`prepare`) for workbook and preview; `title` dropped from the part
- [x] 4b.5 Dates in Excel's built-in short date (numFmtId 14); totals label per function in the conversation language (`language` argument, fr default)
- [x] 4b.6 Limit errors and description tell the model to inform the user and suggest splitting; each call is a new file and card
- [x] 4b.7 Pane: per-column formatters, memoized rows, sticky `thead`, `title` on cells that may clip, arrow-key navigation with one focusable cell
- [x] 4b.8 Display name "Generate an Excel file" / "Générer un fichier Excel" in i18n, Help Center, README, migration note
- [x] 4b.9 Tests: card renderer (register, live auto-open, history replay), preview slice (reset on session change), preview loader (stale URL), backend cases above
- [x] 4b.10 Follow-up issues #3212, #3213, #3214, #3215; #3208 body updated

## 4c. Live-session fixes (2026-10-21, owner-approved)

- [x] 4c.1 Formulas rejected with "formulas are not accepted: send the computed value, and set `total` on the column for sums/averages" (numeric/percent/currency `=` values; text cells calling a function or referencing a cell); description and `rows` schema say literal computed values only
- [x] 4c.2 Row length error states expected and received counts with sheet and row
- [x] 4c.3 Description: call once per file, answer after a success; success text ends with "File created and shown to the user. Do not create it again; reply now."
- [x] 4c.4 Per-turn idempotency: identical repeat call returns the first text, no new file or card
- [x] 4c.5 Description: a sub-agent returns the data to the delegating agent instead of calling the tool (description only; no sub-agent signal in the tool context, general fix #3219)

## 4d. Computed columns (2026-10-21, owner-approved)

- [x] 4d.1 `compute` on a column (`add`, `subtract`, `multiply`, `divide`, `share_of_total`, optional `round`), operands by header name or number; rows send null or omit computed columns (D9)
- [x] 4d.2 Per-row formulas with the row's addresses, `IFERROR` where a result can be empty, `ROUND` for `round`; totals on computed columns
- [x] 4d.3 Validation naming sheet and column: op, unknown/ambiguous header, text/date reference, self/forward reference, missing operand, two numbers, divide by literal 0, `round` range
- [x] 4d.4 Preview values computed with the same semantics; free-formula refusal points to `compute`; tool description with one example
- [x] 4d.5 Help Center en/fr: one sentence and an example

## 4e. Live-session fixes, round 2 (2026-10-21, owner feedback)

- [x] 4e.1 Reject a text cell holding leaked row JSON (`Loyer", 1200, null], [`), naming sheet, row, column; ordinary quoted/bracketed text kept
- [x] 4e.2 Preview carries a formula template per computed column and the totals formula per totals column
- [x] 4e.3 Pane: Excel formula bar (name box, "fx", formula or raw value), updated by click and arrow keys

## 4f. Derived columns sent as literals (2026-10-21, owner feedback)

- [x] 4f.1 Tool description: never compute derived columns yourself, declare them with `compute`; `share_of_total` example; a division by zero leaves the cell empty
- [x] 4f.2 Cheap check after a successful build: a literal numeric column equal (within its own rounding) to add/subtract/multiply/divide of two earlier columns or the share of total of one, on at least 2 of the first 20 rows, is named in the success text with its `compute`; file kept; at most 12 numeric columns checked, 3 hints

## 4g. Manual total row next to the automatic one (2026-10-21, owner feedback)

- [x] 4g.1 Tool description: do not add your own total/subtotal row for columns that set `total`; the totals row is added automatically
- [x] 4g.2 Cheap check after a successful build, never a rejection: a data row whose first text cell is a total-like label (total, totaux, total général, grand total, sum, somme, sous-total, subtotal; or one followed by a word) in a sheet with a `total` column, with its total-column cells empty or equal to the automatic totals over the other rows, is named in the success text (sheet, row); one per sheet; file kept; only a count is logged

## 4h. Charts not supported yet (2026-10-21, owner-approved)

- [x] 4h.1 Tool description: charts are not supported yet; still create the workbook with its data and tell the user (they can insert a chart in Excel)
- [x] 4h.2 Chart-like arguments (top level or per sheet) are ignored, not rejected (the schema already ignores unknown fields); a hidden flag adds the chart note to the success text before "reply now"
- [x] 4h.3 Help Center en/fr "Generate an Excel file": one sentence that charts are not available yet

## 4i. Final review fixes (2026-10-21)

- [x] 4i.1 `round` on a large value no longer overflows `Decimal` (unhandled tool error before)
- [x] 4i.2 A `number` computed column with `round` shows that many decimals in the file and the preview
- [x] 4i.3 An identical repeat call returns the first success text, notes included
- [x] 4i.4 Leaked-row check ignores text with a `[` before the `]` (`Écran 27", 2 ports [HDMI]`)

## 6. Writer swap and cached values (D15, review fix; owner-approved 2026-10-28)

- [x] 6.1 Writer on XlsxWriter (`strings_to_formulas/numbers/urls` off, `use_future_functions` on, `num_format` 14, `quote_prefix`, freeze, auto filter, widths, header style, full recalculation on load); `xlsxwriter` runtime dependency, `openpyxl` to test dependencies; package and fred-agents `uv.lock` (only openpyxl and et-xmlfile leave)
- [x] 6.2 Cached `<v>` for totals and computed columns with today's evaluated values
- [x] 6.3 Tests: every existing read-back test passes unchanged on the new writer; cached values read with `openpyxl.load_workbook(data_only=True)` equal the preview for totals and each `compute` op (incl. empty `IFERROR` results); a `=1+1`, `@SUM(A1)` and URL text stay strings; LibreOffice headless opens the file without repair

## 7. Formula parser, allow-list and references (D13, D14, D17; review fixes)

- [x] 7.1 `formulas.py` tokenizer and parser (A1 refs, ranges, sheet-qualified refs quoted or not, strings, numbers, booleans, errors, operators incl. `&` and `%`, function calls); canonical re-emission with sheet quoting and `''` escaping; `_xlfn.`/`_xlws.` prefixes stripped on input
- [x] 7.2 Validation: allow-list, security refusals (volatile, network/link, environment, XLM, external workbook, DDE `|`), unknown function, defined names, structured refs, R1C1, whole-column/row refs, unknown sheet (lists sheets), out-of-bounds column or row (gives the sheet's letters and row range), range spanning data and totals rows, French names and `;` (English form in the message), length 8 192, depth 32, 5 000 model formula cells, cycles
- [x] 7.3 `_FORMULA_LIKE` replaced by the parser: a plain string that parses as a formula with a function or reference (`='Données 2025'!B2`, `=Synthèse!B2`, `=[x.xlsx]S!A1`, `=cmd|…`) is refused with the formula-cell form or the security message; other trigger text stays literal
- [x] 7.4 Text cells, headers and sheet names with DDE or external-workbook patterns refused (D17), full-width signs included; `- point`, `+33 6…`, `a|b`, `=== x ===` kept
- [x] 7.5 Tests: one case per refusal (message names sheet, row, column and the fix), quoting matrix (`Données 2025`, `Synthèse`, `Q1`, `It's`, `Data_1`), accepted forms round-trip to canonical text

## 8. Evaluator and formula surfaces (D13, D15, D16)

- [x] 8.1 Evaluator for the D14 allow-list with Excel semantics (empty cells, booleans, error propagation, criteria with wildcards, case-insensitive text, date serials, `ROUND` half away from zero), dependency order across sheets, range materialized once, per-range index for the `*IF(S)` family, 2 000 000 cell-read budget with a limit error
- [x] 8.2 Dynamic arrays `FILTER`/`SORT`/`UNIQUE`: evaluated spill, written with `write_dynamic_array_formula`; spill into a non-empty cell or past the sheet's columns or row limit refused
- [x] 8.3 Column `formula` (first data row, filled down with relative shift) and formula cells `{"formula": ...}` in the tool schema and `prepare`; rows send null for formula columns; column type gives the number format
- [x] 8.4 `compute` and `total` compiled to formula ASTs; delete `_formula`'s string building, `_evaluate`, `_apply`, `_operand_value` and the preview's own totals arithmetic; same formula text as before
- [x] 8.5 Cached values for every formula (errors as error values); preview cells from the evaluator, `cell_formulas` sparse map for formula cells; pane formula bar shows them (vitest)
- [x] 8.6 Tool description: formula forms, English names and commas, summary-sheet example with a quoted sheet name, `total`/`compute` first for simple cases; schema size measured before/after and recorded (target: under +40 %)
- [x] 8.7 Tests: each allowed function against hand-checked values (and LibreOffice headless on a sample workbook for the functions it supports); summary sheet with `SUM`/`SUMIFS`/`XLOOKUP` over two data sheets, cached values read back; `FILTER` spill and collision; prefixes in `xl/worksheets/sheet*.xml` (`_xlfn.XLOOKUP`, `_xlfn._xlws.FILTER`); budget error; 50 000-cell workbook with a `SUMIF` column builds in under 1 s

## 9. Revisions (D10, D11, D12)

- [ ] 9.1 (partly done: single head, upgrade/check/downgrade on a scratch SQLite file; the real `python -m fred_runtime migrate` on the shared dev database waits for the owner's go) `WorkbookSpecStore` (`Sql`/`Memory`, provider hook), `cap_spreadsheet_workbook` model, Alembic tree `spreadsheet_migrations/` with one initial revision, `manifest.tables` and `migrations_location()`; `alembic heads` = 1 and a real `python -m fred_runtime migrate` on a local database (with the owner's go-ahead: the dev database is shared with the running app)
- [x] 9.2 `changes` schema (flat change objects, nested parts validated in code), mutually exclusive with `sheets`; `file_name`/`language` default to the base's; tool description: a change the user asks for goes in `changes`, which keeps everything else as delivered (replaces "call it again with the complete corrected data")
- [x] 9.3 Apply on the base: ops of D10 resolved on base numbering and names, applied as one step; `where` matching; formula reference adjustment for row/column insert and removal, appended rows, sheet rename; dependent-formula refusals; all errors listed with change index and fix; no base, nothing changed, base too large
- [x] 9.4 Base read once per turn (closure), upsert after delivery, failures handled as D11; per-turn identical-call guard keyed with `changes` and base version; one-line structure summary in the success text (600 chars max)
- [x] 9.5 Versions: `workbook_id`/`version` rules, `-vN` visible names, part fields; frontend slice keeps the latest version per workbook, card chip "Latest version"/"Dernière version" and "Version n", pane header version; en/fr strings
- [x] 9.6 Tests (backend): one per op incl. computed column add, split by `where` into a new sheet, move to an existing sheet, rename with cross-sheet formulas rewritten, row insert inside a summed range, append after a range ending on the last data row, refused removal of a referenced column/sheet, each error message; base survives a new tool instance (next turn) through the memory store; Graph assembly with a `changes` call; spec size cap
- [x] 9.7 Tests (frontend): latest chip moves to a new card live and on history replay; older card still downloads its file
- [x] 9.8 `fred-performance-reviewer` on the tool call site (database read/write, evaluator budget, writer)

## 10. Docs for the extension

- [x] 10.1 Help Center en/fr "Generate an Excel file" / "Générer un fichier Excel": ask for changes to the last file (versions, latest marker), formulas and a summary sheet, what is not available (non-technical wording)
- [x] 10.2 Package README, `docs/swift/capabilities/AUTHORING.md` row (owns a table), `docs/swift/ops/DATABASE_MIGRATIONS.md` row (`cap_spreadsheet_alembic_version`)
- [x] 10.3 Migration note `3208-spreadsheet-capability.md`: `impact: minor` (new Alembic revision, applied by the standard fred-agents migration hook), table and rollback (table left in place, unused by an older image), openpyxl removed from the image; `make migration-check`
- [ ] 10.4 Live check on mistral-medium (ReAct, Deep, Graph): add a column, add rows, split into two sheets, summary sheet with cross-sheet formulas; file opens in Excel/LibreOffice without repair and a non-recalculating reader shows the values; record evidence

## 5. Docs and release

- [x] 5.1 `docs/swift/capabilities/AUTHORING.md` one row; package README
- [x] 5.2 Migration note (`docs/swift/ops/MIGRATION-GUIDES.md`): new admin-gated capability, new dependency in fred-agents
- [ ] 5.3 Record verification evidence, archive the change, close #3208

## Verification evidence

2026-10-21, branch `feat/spreadsheet-capability`:

- Package `fred-capability-spreadsheet`: `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors); `make test` 46 passed (workbook read back: typed values and formats, currency symbols, percent decimals, bold frozen header, auto filter, declared/computed/capped widths, SUM/AVERAGE/MIN/MAX/COUNTA formulas with column formats, no totals without data, injection guard with quote prefix, multi-sheet, every structure/conversion error naming sheet/row/column, every limit and the inclusive 5000-row bound; tool: registry `validate()`, entry point, manifest admin-gated with `("react", "graph")`, schema without `$defs`, Graph `build_capability_agent_block` exposes the tool, file written under `spreadsheets/<session>/` with xlsx MIME, download `LinkPart`, `is_error` and no write on invalid input, missing port, storage failure, artifact kept through a LangChain tool call; concurrency bound: with 4 builds blocked in their worker, a fifth call fails fast with a busy error, then the 4 complete and the counter returns to 0).
- fred-agents: `boot_capability_registry()` lists `spreadsheet`; `make code-quality` green; `make test` 134 passed, 6 xfailed (`_SHIPPED_CAPABILITY_IDS` updated). `uv lock` adds only the package, `openpyxl 3.1.5` and `et-xmlfile 2.0.0`.
- Frontend (worktree install): `make code-quality` green (tsc, prettier, eslint); vitest on AgentFormModal, helpCenter: 152 passed (new pack test).
- Sample workbook: 50 000 cells built in 0.31 s (139 KB); input validation of that size 3.5 ms. LibreOffice headless conversion (PDF and CSV): totals computed (4, 16.3 %, 1 550,50 €, $1 300,25), `=1+1` and `@cmd` shown as text, no repair prompt.
- `fred-performance-reviewer`: no blocking call on the event loop (generation and validation in `asyncio.to_thread`; argument parsing at the 50 000-cell limit is 3.5 ms); upload uses the existing async workspace client; no new metric or label; tool latency covered by the existing tool observability middleware. Concurrent builds bounded per pod at 4 by a module-level fail-fast counter mirroring PPT Filler's heavy-job slot (no queueing, not configurable, like PPT Filler's).
- `make migration-check`: 1 new declaration valid (`impact: none`).
- Divergence from the draft: byte-identical output dropped (openpyxl stamps zip and core-property times; tests read back instead). Not done: 4.4 live check, 5.3 archive.

Fix pass, 2026-10-21 (after review "ready with fixes" and the owner's spec review):

- Package: `make test` 84 passed (new: control characters stripped/rejected, `History` reserved, header length, ambiguous comma for number/currency/integer/percent, non-finite numbers, unambiguous separators still parse, `#`/`%` file names, built-in date format checked in `xl/styles.xml` (`numFmtId="14"`, no custom entry), totals label per function and language in file and preview, limit hint, single conversion; tool: `language` in the schema and not required, description wording, label through the tool, control character never escapes); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).
- fred-agents: `make test` 134 passed, 6 xfailed.
- Frontend: `tsc --noEmit` clean; prettier and eslint clean on the touched files; vitest on `features/capabilities`, `features/helpCenter` and `AgentFormModal`: 49 files, 420 tests passed (spreadsheet: pane incl. arrow-key navigation and clipped-cell titles, per-column formatter count, card renderer, slice, preview loader).
- LibreOffice headless CSV of a French workbook: date shown as `31/01/2026` (reader locale), totals label `Moyenne` with the computed average, control character stripped, no repair prompt.
- Not done: 4.4 live check (ReAct and a Deep agent delegating to a sub-agent), 5.3 archive.

Live-session fix pass, 2026-10-21 (session 41fde1b9, Deep agent on mistral-medium-latest):

- Package: `make test` 94 passed (new: 8 formula cases across number/percent/currency/integer and text `=HYPERLINK(`, `= sum(`, `=$B$2`, `=B2/B3`, each naming sheet/row/column and the exact message; `=== Section ===`, `+1`, `@SUM(A1)` and `=1+1` still stored as literal text; row mismatch "expected 3 values (one per column), got 4"; success text ending; identical repeat (also with `.xlsx` suffix) returns the first text with no write and no card; changed rows or a rebuilt tool write a new file); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).
- Not covered here: sub-agent cards never reaching the chat on Deep agents is a runtime issue, tracked separately.
- Sub-agent guidance (4c.5): package `make code-quality` green, `make test` 94 passed (description asserts the sub-agent sentence).

Computed columns, 2026-10-21:

- Package: `make test` 121 passed (new: formula and preview value per op (`=C2-B2`, `=B2+10`, `=C2*1.2`, `=C2*(-2)`, `=IFERROR(C2/B2,"")`, `=IFERROR(ROUND(C2/3,1),"")`, `=IFERROR(C2/SUM($C$2:$C$4),"")`, `*` alias with case-insensitive header and `"2"`, `"15%"` operand); per-row and per-sheet addresses on two sheets; default number/percent formats; `SUM`/`COUNT` totals and preview totals over computed columns; chained computed columns and empty-result propagation; null placeholder, omitted and pre-filled computed cells; `ROUND` half away from zero (2.675 → 2.68, -0.125 → -0.13); 11 compute errors naming sheet and column; forward reference, text type, duplicate header; refusal message points to `compute`; tool description); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).
- LibreOffice headless CSV of a two-sheet workbook (subtract, divide + round with a 0 and an empty divisor, share of total, a chained multiply by -1.5, totals, a second sheet with a rounded share): every recalculated value equals the preview (`20`, `1,2`, `60%`, `-1,8`, empty for the zero/empty divisors and their dependants, totals `100`/`200`/`100%`, `14,3% 28,6% 57,1%`).

Live-session round 2, 2026-10-21 (session 78bfa4f2, Deep agent on mistral-medium-latest):

- Root cause of "null null null": the stored `Budget_Realisation-680539b6.preview.json` holds the text cell `Loyer", 1200, 1150, null, null, null], [` followed by `8000, 8400`: the model's quote closed "Loyer" early, so the row's JSON tail landed in one cell and the next row lost its label. Not a frontend `null` rendering (JSON null renders empty).
- Package: `make test` 131 passed (new: the live rows rejected with sheet/row/column and the message; three leak fragments caught; quoted/bracketed text and `"null"` kept; formula templates equal the file's formula on every row, share range absolute, totals formula equal to the file's, none on literal columns; totals formulas cover rows beyond the preview cap, `COUNTA` on text); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).
- Frontend: `tsc --noEmit`, prettier and eslint clean on the spreadsheet feature; vitest on `features/capabilities/spreadsheet`: 5 files, 30 tests passed (new: formula bar for computed and totals cells by click and arrow keys, computed value in the cell, raw literal values, empty cell never "null"; `formulaBarText` unit cases incl. French decimal and percent).

Live-session round 3, 2026-10-21 (session 1e3ef259, Deep agent on mistral-medium-latest):

- Root cause of "no formula on Taux de réalisation / Part du total du réel": the stored `create_spreadsheet` call (session_history rank 2) sent no `compute` at all; every derived column was a literal (`-50, 0.9583, 0.1144`...). The model's reasoning says share of total "is not a column" so compute cannot express it, and that divide would fail on the 0 budget. Not a preview or formula-bar bug: no formula exists for those columns.
- Package: `make test` 135 passed (new: the live rows name Écart → subtract, Taux → divide, Part → share_of_total; computed and independent columns get no hint; a single matching row or a copied operand is no derivation; the tool keeps the file and returns the note before "reply now"; description asserts the derived-column rule, `share_of_total` and the division-by-zero sentence); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).

Live-session round 3 follow-up, 2026-10-21 (session 1e3ef259): the model also sent its own "Total" row with empty values on top of `total: sum`, so the file held an empty "Total" row above the real totals row.

- Package: `make test` 139 passed (new: an empty "Total" row named with sheet and row; filled "Total HT"/"Total TTC" rows equal to the totals named once per sheet; a "Total" row with other values, "TotalEnergies", and a sheet without `total` columns get no note; the tool keeps the file and returns the note before "reply now"; description asserts the no-own-total sentence); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).

Charts not supported yet, 2026-10-21:

- Package: `make test` 143 passed (new: `chart` at top level, `Charts` at top level and `graph` on a sheet, each through a LangChain tool call: file and card written, chart note in the success text before "reply now"; no note without chart arguments; schema keeps exactly `file_name`, `sheets`, `language` and the description asserts the chart sentence); `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors).
- Frontend: prettier clean on the two Help Center files.

Revisions and formulas, 2026-10-28 (owner decisions recorded in design.md; commits 6476d2e8b..a26af7a28):

- Package: `make code-quality` green (ruff, import order, format, bandit, detect-secrets, basedpyright 0 errors); `make test` 364 passed: workbook 156 (existing cases unchanged on the XlsxWriter writer except the column-width reading, cached values read with `data_only=True`, strings never turned into formulas, numbers or links, sheet-qualified/DDE/external text refused, model formulas: fill-down with `_xlfn.XLOOKUP` in the sheet XML and cached values, summary sheet over two sheets, canonical quoting of `'Synthèse 2025'`, `FILTER` spill with `cm="1"` and `ref="A2:B2"`, spill collision, refusals naming sheet/row/column and the fix, plain-string formula answered with the formula-cell form, quoted `"SORT("` kept, text type inferred, compute on a formula column wrapped in `IFERROR`, formula-cell limit, per-cell formula-bar entries, `$` hint), formulas 62 (quoting matrix, canonical round trips, stored prefixes, 28 refusals, length, fill-down bounds, formula-like strings), evaluator 96 (every allowed function against hand-checked Excel results, spills, approximate lookup on unsorted data refused, cycle, running total linear via `=B1+A2`, `SUM($A$2:A2)` over 5 000 rows stopped by the budget with a remedy, a 5 000-row `SUMIF` column under a quarter of the budget, 1900 serials), revisions 23 (each op, split by `where`, move to an existing sheet by header, rename rewriting references, range widen/shift/shrink as Excel, refused break of a referenced cell or computed column, all errors at once, conflicts, nothing changed; through the tool: base in a later turn from the store, no base, both modes, bad changes keep the base, repeated changes applied once, memory-only without agent identity, too-large base, Graph-assembled tool with `changes`, `-v2`/`-v3` names and part fields), store 2 (SQL on in-memory SQLite and memory), capability 25 (schema: `changes` added, nothing required; description; migrations location).
- Alembic: `make db-check-heads` single head; `alembic upgrade head`, `alembic check` (no drift) and `alembic downgrade base` on a scratch SQLite file (not the shared dev database). Tree added to the root Makefile combined checks and `Check-migrations.yml`.
- fred-agents: `make test` 135 passed, 6 xfailed; `uv lock` removes `openpyxl` and `et-xmlfile`, adds nothing (XlsxWriter 3.3.0 already locked through python-pptx).
- Frontend (worktree's own node_modules): vitest on `features/capabilities/spreadsheet` 5 files, 34 tests passed (formula bar from `cell_formulas`, error values kept, latest-version marker live and on replay, no marker for a single version, slice keeps the highest version per workbook and resets per conversation); prettier and eslint clean; `tsc --noEmit` reports one error outside this change (`MermaidBlock` imports `beautiful-mermaid`, missing from this worktree's older node_modules).
- Performance: tool schema 6 160 -> 8 084 characters (+31 %, under the +40 % target); 50 000 cells with 35 000 compute formulas: prepare and evaluate 0.28 s, write 0.36 s (XlsxWriter's per-formula regex rewrite bypassed: formulas are emitted in stored form). `fred-performance-reviewer` checklist: build, evaluation and preview in `asyncio.to_thread` under the 4-build slot; finding fixed in a26af7a28: applying changes and serializing the request (~180 ms at the cell limit) ran on the event loop, now in a worker thread; database: one `SELECT` on the first call of a turn, one `UPDATE` (or `INSERT`) per delivery, async SQLAlchemy on the pod's own engine (one more small pool, as writable_document); turn state lives in the per-turn tool closure, the base in Postgres (replica-safe), `_active_builds` stays pod-local and documented; no new metric or label, tool latency covered by the existing tool observability middleware.
- LibreOffice 26.2 headless CSV of a four-sheet sample (`XLOOKUP` column, `SUMIFS`/`COUNTA` summary, `FILTER` spill, totals): every recalculated value equals the cached value and the preview; no repair prompt.
- Divergences from the scoping text, recorded in design.md "Implementation notes": dollar-free ranges anchored in column formulas; formulas sent in `changes` are written for the resulting workbook; a row cannot be edited and moved in one call; rows inserted above a range shift it (Excel); a repeated `changes` call in a turn is deduplicated on its arguments; XlsxWriter stores any formula naming a dynamic-array function (`XLOOKUP` included) as a one-cell dynamic array; the preview of an `AVERAGE` over no number now shows `#DIV/0!` as Excel does.
- Not done: 9.1 real migration run on the shared dev database (owner's go), 10.4 and 4.4 live checks, 5.3 archive.

