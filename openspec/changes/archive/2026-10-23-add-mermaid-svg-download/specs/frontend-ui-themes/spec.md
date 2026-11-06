## ADDED Requirements

### Requirement: Mermaid diagrams can be downloaded with their active theme

Successfully rendered Mermaid diagrams SHALL offer a translated, keyboard-accessible SVG download action as the second action in inline and fullscreen views. The downloaded `diagram.svg` SHALL contain the entire diagram, have a white background, use the selected theme's light palette, preserve labels and local SVG references, and remain readable in a browser outside Fred without the application's stylesheets. Export SHALL run locally without fetching assets, changing the preview or exposing unrelated page content. Loading or failed renders SHALL NOT offer an active download. An export failure SHALL show translated feedback while retaining the diagram and its existing actions.

#### Scenario: Preferred-renderer diagram download

- **WHEN** a user downloads a rendered flowchart from its inline preview
- **THEN** a standalone SVG containing all nodes, labels and connectors is downloaded
- **AND** its full diagram bounds and selected theme are preserved on white

#### Scenario: Compatibility diagram and fullscreen

- **WHEN** a user downloads an official compatibility diagram from fullscreen
- **THEN** the SVG retains its labels, theme and local marker or gradient references outside Fred
- **AND** fullscreen remains open until the user closes it normally

#### Scenario: Theme changes before download

- **WHEN** the user changes theme or mode and downloads the updated diagram
- **THEN** the file uses the newly selected theme's light palette on white, independently of the interface mode

#### Scenario: Unavailable rendering and failed export

- **WHEN** the diagram is still loading or cannot render
- **THEN** downloading an incomplete or stale diagram is unavailable
- **AND WHEN** an export of a rendered diagram fails
- **THEN** translated feedback is shown without losing the preview, source copy or fullscreen action
