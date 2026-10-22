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

When a column declares a total (`sum`, `average`, `min`, `max`, `count`), the system SHALL add one totals row after the data whose cells are Excel formulas over that column's data range, formatted like the column. The row's label SHALL name the functions used, in the conversation language: Total, Moyenne, Min, Max, Nombre in French (the default) and Total, Average, Min, Max, Count in English.

#### Scenario: Sum of a currency column

- **GIVEN** a `currency` column with `total: "sum"` over rows 2 to 11
- **WHEN** the workbook is generated
- **THEN** row 12 holds `=SUM(C2:C11)` in that column and "Total" in the first text column

#### Scenario: Label follows the function and the language

- **GIVEN** a column with `total: "average"`
- **WHEN** the workbook is generated for a French conversation
- **THEN** the totals label reads "Moyenne", and "Average" for an English conversation

### Requirement: Invalid input is returned to the model

The system SHALL reject invalid input with an error tool result that names the sheet, row and column at fault, and SHALL NOT write any file in that case. Invalid input includes an empty, duplicated, over-31-character or reserved (`History`) sheet name, a name containing `[ ] : * ? / \` or control characters, a row whose length differs from the column count, a value that cannot be converted to its column type, a non-finite number, a formula (any `=` value in a number, integer, percent or currency column, or a text cell such as `=SUM(B2:B6)` or `=B2/B3` that calls a function or references a cell), a number whose lone comma could separate thousands or decimals (`"1,234"`), and a text value holding other cells' JSON (a quote inside the text that closed it early, such as `Loyer", 1200, null], [`), which would otherwise shift the row's values into the wrong cells. Control characters in cells and headers SHALL be removed, never raised as an error.

#### Scenario: Row length mismatch

- **WHEN** the model sends a row with four values for a three-column sheet
- **THEN** the tool returns an error naming the sheet and row with the expected and received value counts, no file is written, and the model can call the tool again in the same turn

#### Scenario: Formula sent as a cell value

- **WHEN** the model sends `=B2/SUM($B$2:$B$6)` in a percent column
- **THEN** the tool returns an error saying formulas are not accepted in cells, asking for the computed value and pointing to the column `compute` for per-row calculations and to the column `total` for sums and averages, and no file is written

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

A column MAY declare `compute` instead of row values: `add`, `subtract`, `multiply` or `divide` between `left` and `right` (each a column header of the same sheet or a number), or `share_of_total` of one `column` (its value divided by that column's total), with an optional `round` (0 to 10 decimals). The system SHALL write one formula per data row using that row's cell addresses on the same sheet and only the `SUM`, `ROUND` and `IFERROR` functions; a result that can divide by zero, or that uses a computed column that can be empty, SHALL be wrapped in `IFERROR(...,"")`. Rows SHALL accept either `null` (any value is ignored) or no value at all for computed columns. A computed column without an explicit type SHALL be `number` (`percent` for `share_of_total`); a column `total` SHALL apply to it as to any numeric column. A `number` computed column with `round` SHALL show that many decimals. The preview SHALL hold the values the formulas yield (an empty source cell counts as 0, a division by zero is empty, `round` rounds halves away from zero). The system SHALL reject, naming the sheet and column and the fix, an unsupported op, a header that matches no column or several columns, a reference to a text or date column, to its own column or to a computed column placed after it, a computed text or date column, a missing operand, two number operands, a division by a literal 0 and a `round` outside 0 to 10.

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

The system SHALL write `.xlsx` only (never macro-enabled formats), SHALL write formulas only in the totals row and the computed columns it generates, and SHALL store any accepted text cell starting with `=`, `+`, `-`, `@`, tab or carriage return as literal text.

#### Scenario: Data that looks like a formula

- **GIVEN** a text cell `=== Section ===` or `@SUM(A1)`
- **WHEN** the workbook is generated
- **THEN** the cell holds that literal string and no formula

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
- **THEN** a new `.xlsx` and a new card are produced and the previous file stays available

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
