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
