## ADDED Requirements

### Requirement: Agents create Excel workbooks on request

When the `spreadsheet` capability is enabled on an agent, the agent SHALL offer a `create_spreadsheet` tool that produces an `.xlsx` workbook and delivers it to the user as a download in the conversation. The capability SHALL work on ReAct, Deep and Graph agents.

#### Scenario: User asks for an Excel file

- **GIVEN** an agent with the `spreadsheet` capability enabled
- **WHEN** the user asks for a list of items "as an Excel file"
- **THEN** the agent calls `create_spreadsheet` and the conversation shows a download chip for a `.xlsx` file
- **AND** the file opens in Excel and LibreOffice without a repair prompt

#### Scenario: Graph agent selects the capability

- **WHEN** an author enables the capability on a Graph agent
- **THEN** assembly succeeds and the tool is available to the graph

### Requirement: Columns are typed and the sheet is formatted

The system SHALL apply each column's declared type as an Excel number format (`text`, `number`, `integer`, `percent`, `currency`, `date`), show a `currency` column's declared currency (`EUR`, `USD`, `GBP`, `CHF`, `JPY`, `CNY`, `CAD`, `AUD`) as a symbol in its number format, style and freeze the header row, add an auto filter over the data, and set each column width from its declared value or from its content, capped.

#### Scenario: Typed columns

- **GIVEN** a sheet with a `date` column holding `"2026-10-21"` and a `percent` column holding `0.15`
- **WHEN** the workbook is generated
- **THEN** the date cell holds a date value with a date format and the percent cell holds `0.15` displayed as `15%`

#### Scenario: Currency symbol

- **GIVEN** a `currency` column with `currency: "EUR"` holding `1234.5`
- **WHEN** the workbook is generated
- **THEN** the cell holds the number `1234.5` with a number format showing the `€` symbol and two decimals
- **AND** a `currency` column without `currency` uses a two-decimal format without symbol

#### Scenario: Header stays visible

- **WHEN** the workbook is generated
- **THEN** the first row is bold and frozen

### Requirement: Totals are live formulas

When a column declares a total (`sum`, `average`, `min`, `max`, `count`), the system SHALL add one totals row after the data whose cells are Excel formulas over that column's data range, formatted like the column.

#### Scenario: Sum of a currency column

- **GIVEN** a `currency` column with `total: "sum"` over rows 2 to 11
- **WHEN** the workbook is generated
- **THEN** row 12 holds `=SUM(C2:C11)` in that column and "Total" in the first text column

### Requirement: Invalid input is returned to the model

The system SHALL reject invalid input with an error tool result that names the sheet, row and column at fault, and SHALL NOT write any file in that case. Invalid input includes an empty, duplicated or over-31-character sheet name, a name containing `[ ] : * ? / \`, a row whose length differs from the column count, and a value that cannot be converted to its column type.

#### Scenario: Row length mismatch

- **WHEN** the model sends a row with four values for a three-column sheet
- **THEN** the tool returns an error naming the sheet and row, no file is written, and the model can call the tool again in the same turn

### Requirement: Size limits are enforced

The system SHALL refuse a workbook above 10 sheets, 50 columns per sheet, 5 000 rows per sheet, 50 000 cells in total, 2 000 characters per cell, or 10 MB of output, with an error tool result stating the limit. It SHALL never truncate data silently.

#### Scenario: Too many rows

- **WHEN** a sheet holds 5 001 rows
- **THEN** the tool returns an error stating the 5 000-row limit and no file is written

### Requirement: Generated workbooks run no code

The system SHALL write `.xlsx` only (never macro-enabled formats), SHALL write formulas only in the totals row it generates, and SHALL store any text cell starting with `=`, `+`, `-`, `@`, tab or carriage return as literal text.

#### Scenario: Data that looks like a formula

- **GIVEN** a text cell `=HYPERLINK("http://example.test","x")`
- **WHEN** the workbook is generated
- **THEN** the cell holds that literal string and no formula

### Requirement: Authors enable it from the agent form

The agent form SHALL offer the capability as a toggle in the Advanced view and as a "Create an Excel file" pack in the Simple view's Document production section, subject to the team's capability availability. The capability SHALL be admin-gated: a platform administrator opens it per team.

#### Scenario: Enable from the Simple view

- **WHEN** an author turns on the "Create an Excel file" pack for a team that can use the capability
- **THEN** the agent's capability selection contains `spreadsheet`
