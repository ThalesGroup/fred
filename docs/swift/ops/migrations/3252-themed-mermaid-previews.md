---
schema: 1
title: "Render Mermaid previews with the active Fred theme"
impact: none
configuration: none
configuration_reason: "Only frontend diagram rendering changes; existing UI theme tokens are reused without new settings."
no_action_reason: "Existing Markdown source and APIs are unchanged; the new preview takes effect with normal frontend deployment."
---

## Applicability

Fred deployments displaying Mermaid blocks through the shared Markdown renderer.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Shipped and deployment themes retain their existing tokens.

## Upgrade

Deploy Fred normally. No stored diagram source or conversation data needs conversion.

## Validation

Open a wide Mermaid flowchart in a conversation: the unframed inline preview must fit without cropping while surrounding prose keeps its reading width. Use its fullscreen icon, change the UI theme and light/dark mode, and verify both views follow the active theme. Escape must close fullscreen and restore focus. Copy must return the original source. Also open pie, Gantt, mindmap, journey and timeline diagrams to verify the compatibility rendering path, including visible connectors and theme colors in dark mode.

## Rollback

Use the normal frontend image rollback procedure. This change introduces no data migration.

## Limitations

The preferred renderer covers a conservative subset of flowchart, sequence, state, class, ER and XY syntax. Other supported Mermaid constructs retain the official Mermaid compatibility renderer. Diagram-specific palette selection and new export or pan/zoom features are not added.
