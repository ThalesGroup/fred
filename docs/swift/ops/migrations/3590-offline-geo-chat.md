---
schema: 1
title: "Render shared geo tool results as offline maps in chat"
impact: none
configuration: none
configuration_reason: "The geo tool is built into the agent runtime and the Leaflet world map is bundled with the frontend; no deployment values or secrets change."
no_action_reason: "Existing conversations and agent configurations remain valid; normal deployment supplies the new tool and local map assets without a data migration."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the agent pods and frontend normally. Agents can call `geo.render_points` after their updated pods start.

## Validation

Ask a ReAct, Deep or Graph agent to map named coordinates. Confirm that the tool call appears and its result renders as a Leaflet map with the bundled basemap. Ask for a zone from at least three selected GPS points and confirm that a closed, lightly filled boundary appears while the point markers remain. Disable browser network access after loading the chat and confirm that the map remains usable.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The bundled basemap includes world relief, roads, rivers, lakes, and cities, but lacks street-level detail. The map does not load remote tiles. The agent selects points from available corpus search results; this tool does not exhaustively extract every coordinate from the corpus.
