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

**Non-Goals:** charts, conditional formatting, merged cells, multiple tables per sheet, editing existing workbooks, templates, free-form formulas, editing in the preview, server-side export of query results.

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

openpyxl in a worker thread (`asyncio.to_thread`), validation included, so the event loop never blocks. Header: bold, neutral fill, bottom border; `freeze_panes="A2"`; `auto_filter` over header and data. Number formats: integer `#,##0`, number `#,##0.00`, percent `0%` (up to two decimals when the values need them), currency `#,##0.00` with the symbol (`#,##0.00 "€"`, `"$"#,##0.00`, `"¥"#,##0`, ...), date: built-in `numFmtId 14` (written as `mm-dd-yy`, shown by Excel and LibreOffice in the reader's short-date format). Widths: declared (clamped 4..100), else `min(max(len(header), longest cell) + 2, 60)`. Totals row: bold, label in the first text column without a total naming the functions used, in column order without repeats and in the conversation language (fr: Total, Moyenne, Min, Max, Nombre; en: Total, Average, Min, Max, Count; e.g. "Total / Moyenne"), `=SUM(B2:B{n})` etc. in the flagged columns (`COUNTA` for a text column's count), with the column's number format. Workbook `creator="Fred"`. `prepare` validates and converts every value once (control characters stripped from text cells and headers); the writer and the preview both read its result, so one error context serves both. Byte-identical output is not a goal: openpyxl stamps zip and core-property times; tests read the workbook back instead.

### D4. Validation and limits

Rejected with an `is_error` result naming sheet / row / column: sheet name empty, longer than 31, containing `[]:*?/\` or control characters, starting or ending with `'`, `History` (reserved by Excel), or duplicated (case-insensitive); a header over 2 000 characters; an ambiguous or non-finite number; zero columns; a row longer or shorter than the columns; a value not convertible to its column type; a `sum`/`average`/`min`/`max` total on a text or date column. Limits: 10 sheets, 50 columns, 5 000 rows per sheet, 50 000 cells in total, 2 000 characters per cell, 10 MB output. Rows are never truncated silently: a limit error tells the model to state the limit to the user plainly and suggest splitting the data, and the tool description says so too.

### D5. Formula-injection guard

Only the totals row holds formulas, generated by code. A model-written formula is rejected, not stored (owner decision 2026-10-21, after a live Deep-agent session where 7 of 17 calls sent `=SUM(B2:B6)` or `=B2/SUM($B$2:$B$6)` as values): any `=` value in a number, integer, percent or currency column, and a text cell matching `^=\s*` followed by a function call or a cell reference, return "formulas are not accepted: send the computed value, and set `total` on the column for sums/averages". The message names the real argument (`total` on a column) rather than a `totals` option that does not exist. Any other text cell starting with `=`, `+`, `-`, `@`, tab or carriage return is written as a literal string with the quote prefix, so data from documents or users cannot run as a formula.

### D6. Delivery

Path `spreadsheets/<session_id>/<file_name>-<short uuid>.xlsx` (the name drops `<>:"|?*`, and `#` and `%` as a stopgap for #3213); each call writes a new file and returns a new card, nothing is overwritten, through `workspace_fs.write(..., content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")`. The tool returns the preview card (D8), or the download `LinkPart` when no preview was stored, and a text result telling the model a download button is shown, so it does not write a link itself (PPT Filler wording). Missing `workspace_fs` or a write failure → `is_error` result, logged.

### D7. Model steering without middleware

The tool description carries the steering ("when the user asks for an Excel file, spreadsheet, .xlsx or a table to download, call this tool; never paste a Markdown table instead"; literal computed values only, no formulas; call once per file and answer after a success). The success text ends with "File created and shown to the user. Do not create it again; reply now." The same live session had a sub-agent recreate an already-created file 8 times, so the tool also keeps a per-turn map from a SHA-256 of the normalized request (sanitized file name, sheets, language) to the created file name: an identical repeat returns the first text with no new file and no new card. Tools are built per execution request (`_build_capability_block`), so the closure is the per-turn key; nothing crosses turns or pods. Two identical calls racing in parallel can still both write (accepted: cheap guard, not a lock). No middleware, so Graph stays supported. If the live check shows the default model ignoring the tool, the usage block comes from #2708, not from a ReAct-only middleware. On Deep agents the description also tells a sub-agent not to call the tool but to return the data (compact table or JSON) to the delegating agent, which creates one workbook. The tool cannot refuse a sub-agent call itself: Deep sub-agents receive the same tool instances (`subagent_tools` in `deep_runtime.py`) and `CapabilityContext` carries no sub-agent signal; the general fix is #3219.

### D8. In-chat preview (owner decision 2026-10-21, option A)

- In the same worker thread, `build_preview` turns the validated request into JSON: per sheet the columns (type, currency, decimals the Excel format shows, total kind), typed values (dates as ISO strings), the first 500 rows, the full `row_count`, and a totals row computed in Python to mirror `SUM/AVERAGE/MIN/MAX/COUNT(A)` over every row. Display only; the `.xlsx` keeps its formulas.
- The JSON is written beside the file (`<file>.preview.json`) through `workspace_fs`, like PPT Filler's PDF beside its `.pptx`. No new endpoint: the frontend fetches the durable `/fs/download` href with the session bearer.
- The `spreadsheet_preview` part (preview id = storage key, file name, both hrefs) is declared in `manifest.chat_parts` with `SidePanelSpec(widget="spreadsheet_pane")`. A preview build or upload failure is logged and falls back to the `LinkPart`; it never costs the file.
- Frontend plugin `features/capabilities/spreadsheet/`: the card registers the file in a small slice (launcher, restore) and opens the pane on a live creation; the lazy pane renders an Excel-like `<table>` in one scroll area: frozen column letters, row numbers and row 1 (the workbook header, as the file freezes it), the totals row last with its file row number, column widths from the writer's rule measured on the preview rows (no wrapping except a long text column), `Intl` number/currency/percent/date formats in the UI language (one formatter set per column, one formatting pass per sheet), memoized rows so a selection change re-renders only the rows it touches, the whole `thead` sticky at the top, a `title` with the full text on cells that may be clipped, and a name box with the selected cell's address and content. The grid has one focusable cell (the selection); arrow keys move it. Sheet tabs sit in a fixed bottom strip (`tablist`, arrow keys), with scroll arrows when they overflow. `DataTable` was not reused: it is a paginated list table keyed by column label, without a totals row or frozen headings.

## Risks / Trade-offs

- Large tables cost output tokens: rows pass through the model. Mitigation: limits and Help Center wording; the server-side export of query results is a separate issue.
- openpyxl does not compute cached formula values: Excel and LibreOffice recompute on open; a reader that only reads cached values (pandas without recalculation) sees empty totals. Acceptable for a download.
- A new dependency in the fred-agents image (openpyxl + et-xmlfile, pure Python).
- Generation runs on the default thread pool, bounded per pod at 4 concurrent builds (fail fast over the bound, as PPT Filler); the 50 000-cell limit keeps one call to well under a second.
- Each file now writes two objects (the `.xlsx` and its preview, at most a few hundred KB for 500 rows x 50 columns); the preview shows in the agent workspace listing next to the file, as PPT Filler's PDF does.

## Known limitations

- Erasing a conversation leaves its `.xlsx` and `.preview.json` in workspace storage, as for PPT Filler outputs (#3212).
- The card auto-opens the pane with the shared page-load heuristic of the other capability cards (#3214).

## Out of scope / later

See the proposal's list; ranked roadmap in #3215.

## Follow-ups

- #3212 Generated files (spreadsheet, PowerPoint) survive conversation erasure
- #3213 Workspace download links break on file names containing # or %
- #3214 Deduplicate the capability card auto-open heuristic (4 copies)
- #3215 Spreadsheet capability v2 roadmap
