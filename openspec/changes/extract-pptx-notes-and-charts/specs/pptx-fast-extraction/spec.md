## ADDED Requirements

### Requirement: Fast PPTX extraction keeps speaker notes and chart data
The fast PPTX extractor SHALL append each slide's non-empty speaker notes and SHALL render each native chart as its title, type and cached values in a table capped at 50 categories and 10 series. A chart that cannot be read MUST NOT fail the extraction.

#### Scenario: Deck with notes and a chart
- **GIVEN** a deck whose slide carries speaker notes and a column chart
- **WHEN** it is attached to a conversation
- **THEN** the extracted text contains the notes and a table of the chart's categories and series values

#### Scenario: Deck without notes or charts
- **GIVEN** a deck with neither speaker notes nor charts
- **WHEN** it is extracted
- **THEN** the output is unchanged from before this change
