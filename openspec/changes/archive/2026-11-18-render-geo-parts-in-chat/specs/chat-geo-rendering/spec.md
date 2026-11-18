## Purpose

Enables Fred agents to return typed geographic content that the chat displays as an interactive map without interpreting arbitrary message text as map data.

## ADDED Requirements

### Requirement: Shared point-rendering tool

The runtime SHALL expose `geo.render_points` to ReAct, Deep, and Graph agents without requiring each agent to declare the tool or provide a tool invoker. An explicit declaration SHALL produce only one callable instance.

#### Scenario: ReAct or Deep agent uses the shared tool

- **WHEN** an agent has no `geo.render_points` declaration
- **THEN** the point-rendering tool is callable and its typed `GeoPart` reaches the final response

#### Scenario: Graph agent uses the shared tool

- **WHEN** a Graph node calls `geo.render_points` without an agent-level tool declaration
- **THEN** the runtime permits the call and includes the tool's typed UI part in the final response

#### Scenario: Existing declaration

- **WHEN** an agent explicitly declares `geo.render_points`
- **THEN** the runtime exposes it once

### Requirement: Typed geographic content renders as a map

The chat SHALL render a `GeoPart` containing a GeoJSON FeatureCollection as an interactive map, with visible map attribution. Popup labels SHALL be treated as text. The chat SHALL leave GeoJSON contained only in message prose or a code block as text.

#### Scenario: No-LLM test assistant returns a map

- **WHEN** the no-LLM test assistant completes its `geo` or `markdown` scenario
- **THEN** its final `GeoPart` displays an interactive map with the emitted features

#### Scenario: JSON code block remains text

- **WHEN** an agent writes a GeoJSON object in a Markdown code block without a `GeoPart`
- **THEN** the chat displays the code block without interpreting it as a map
