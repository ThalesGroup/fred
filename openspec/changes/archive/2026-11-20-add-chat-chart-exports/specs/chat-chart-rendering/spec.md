## ADDED Requirements

### Requirement: Chart downloads

Chat SHALL offer a download menu with an Excel workbook of the rows stored in a valid chart part and a PNG download of a plotted bar, line, area, or pie chart. Exports SHALL use the displayed chart part without running the source query again. The Excel workbook SHALL retain the stored columns and values without executing text as formulas, and the PNG SHALL contain the rendered graphic on a transparent background. The table view SHALL offer Excel without a PNG action. Export errors SHALL be visible to the user.

#### Scenario: Download chart data
- **WHEN** a user selects Excel from the download menu of a valid chart or table part
- **THEN** an `.xlsx` file contains the part's bounded rows and columns with their scalar types

#### Scenario: Download graphic
- **WHEN** a user selects PNG from the download menu of a valid plotted chart part
- **THEN** the file contains the visible chart as a PNG image with a transparent background

#### Scenario: Restored chart
- **WHEN** a user reopens a conversation with a saved chart part
- **THEN** the same Excel and applicable PNG downloads remain available

#### Scenario: Export failure
- **WHEN** the browser cannot produce the requested file
- **THEN** the user sees a localized error and the chat remains usable
