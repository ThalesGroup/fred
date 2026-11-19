# chat-geo-rendering Specification

## Purpose
Enables Fred agents to return typed geographic content that the chat displays as an interactive map without interpreting arbitrary message text as map data.

## Requirements

### Requirement: Shared point-rendering tool

The runtime SHALL expose `geo.render_points` to ReAct, Deep, and Graph agents without requiring each agent to declare the tool or provide a tool invoker. An explicit declaration SHALL produce only one callable instance.

#### Scenario: ReAct or Deep agent uses the shared tool

- **WHEN** an agent has no `geo.render_points` declaration
- **THEN** the point-rendering tool is callable and its typed `GeoPart` reaches the final response

#### Scenario: Graph agent uses the shared tool

- **WHEN** a Graph node calls `geo.render_points` without an agent-level tool declaration
- **THEN** the runtime permits the call, emits the typed UI part with the tool result, and includes it in the final response when the turn completes without a pause

#### Scenario: Graph agent pauses after a map tool call

- **WHEN** a Graph node calls `geo.render_points` before requesting human input
- **THEN** the awaiting-human event retains the typed UI part so the resumed chat exchange displays the map

#### Scenario: Existing declaration

- **WHEN** an agent explicitly declares `geo.render_points`
- **THEN** the runtime exposes it once

### Requirement: Typed geographic content renders as a map

The chat SHALL render a `GeoPart` containing a GeoJSON FeatureCollection as an interactive map, with a bundled geographic basemap and visible map attribution. Map rendering SHALL work without network access after the application assets have loaded. Point names SHALL appear beside their markers where space permits; all names SHALL remain available in a keyboard-operated list. Additional scalar properties SHALL appear as a short preview on hover and in full on click and in the list. A named point without additional properties SHALL show its name and coordinates on hover. All labels and details SHALL be treated as text. The chat SHALL leave GeoJSON contained only in message prose or a code block as text.

#### Scenario: No-LLM test assistant returns a map

- **WHEN** the no-LLM test assistant completes its `geo` scenario
- **THEN** its final `GeoPart` displays an interactive map with the emitted features

#### Scenario: Network unavailable

- **WHEN** the user opens a `GeoPart` after the frontend assets have loaded and external network access is unavailable
- **THEN** the map, basemap, features, and attribution remain visible without a remote tile request

#### Scenario: Point with additional information

- **WHEN** an agent calls `geo.render_points` with a named point and additional `properties`
- **THEN** the name is visible beside the point where space permits, the additional information appears on hover or click, and the list exposes the same information to keyboard users

#### Scenario: Point without additional information

- **WHEN** an agent calls `geo.render_points` with a named point and no additional `properties`
- **THEN** hovering the marker shows its name and coordinates in a smaller subtitle

#### Scenario: Enlarge and explore a map

- **WHEN** the user enlarges a map in the chat
- **THEN** the map opens in a large Fred dialog, retains its current view, and can be closed with the visible control or Escape
- **AND** scrolling the wheel over either map view changes the map zoom while scrolling outside the inline map continues to move the chat

#### Scenario: JSON code block remains text

- **WHEN** an agent writes a GeoJSON object in a Markdown code block without a `GeoPart`
- **THEN** the chat displays the code block without interpreting it as a map
