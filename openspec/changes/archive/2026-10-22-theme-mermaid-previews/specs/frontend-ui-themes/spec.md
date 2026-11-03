## ADDED Requirements

### Requirement: Mermaid previews follow the active UI theme

Completed Mermaid blocks SHALL use the active UI theme's semantic roles for renderer-supplied background, text, connectors, accents, node surfaces and borders, and SHALL use the application's font family. Inline and enlarged views SHALL have the same appearance. Changing the shipped or deployment theme or light/dark mode SHALL update mounted previews without requiring a page reload or a diagram-specific theme choice.

#### Scenario: Shipped theme and mode change

- **GIVEN** a completed Mermaid diagram is visible
- **WHEN** the user switches between Pebble, Cobalt and Cloud, or changes light/dark mode
- **THEN** its colors and font follow the newly active theme
- **AND** the enlarged view uses the same palette as the inline diagram

#### Scenario: Deployment theme overrides

- **WHEN** a deployment theme overrides Fred's primary, surface, text and outline tokens
- **THEN** Mermaid previews use those effective token values rather than a stock diagram palette

### Requirement: Themed Mermaid previews preserve shared rendering behavior

The themed preview SHALL render supported diagrams without losing their nodes, relationships or labels. Previously renderable Mermaid syntax outside the preferred renderer's supported subset SHALL retain a compatibility rendering path. Raw source SHALL be attempted before syntax repair. Source copying, enlarged viewing, readable error reporting and the existing transition from streaming source to a completed diagram SHALL remain available.

#### Scenario: Common diagram types

- **WHEN** a user views a supported flowchart, state, sequence, class, entity-relationship or XY diagram
- **THEN** the diagram's nodes, relationships and labels are visible in the themed preview

#### Scenario: Compatibility diagram

- **WHEN** a valid Mermaid pie or Gantt diagram, or syntax unsupported by the preferred renderer, is displayed
- **THEN** the compatibility path renders it with the active UI theme's default palette
- **AND** a source rewrite is attempted only if the original source cannot render

#### Scenario: Existing interactions and invalid source

- **WHEN** a rendered diagram is copied or enlarged
- **THEN** copying returns the original source and enlargement preserves the diagram
- **AND WHEN** neither the original nor repaired source can render
- **THEN** the preview shows a readable error without breaking surrounding Markdown

### Requirement: Diagram previews are isolated and use local assets

Diagram content SHALL NOT execute scripts, load remote fonts or leak styles into surrounding UI. SVG references SHALL remain local to each diagram view, including simultaneously mounted diagrams and enlarged copies.

#### Scenario: Multiple diagrams and an enlarged copy

- **WHEN** multiple Mermaid blocks and an enlarged view are mounted together
- **THEN** every SVG reference resolves within its own view
- **AND** other diagrams and surrounding application text retain their own styles

#### Scenario: Untrusted content and offline fonts

- **WHEN** diagram source contains script-bearing markup or the browser cannot access external font services
- **THEN** the content cannot execute code and rendering uses the application's locally supplied fonts
