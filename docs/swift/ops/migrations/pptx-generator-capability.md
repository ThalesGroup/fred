---
schema: 1
title: "Add the PPTX Generator capability for from-scratch PowerPoint decks"
impact: none
configuration: none
configuration_reason: "A new capability package installed in the Fred Agents image; it adds no configuration keys, chart values, secrets or permissions."
no_action_reason: "The capability is inactive until a team enables it and an agent selects it; it owns no table, so normal deployment needs no data migration."
---
## Applicability

Fred deployments that want agents to generate PowerPoint decks without an
uploaded template (`pptx_generator`). Deployments that do not enable it are
unaffected.

## Prerequisites

The Fred Agents image already ships LibreOffice, used for the PDF preview. No
other prerequisite.

## Configuration

No configuration changes are required. An agent author can optionally upload a
brand template (`.pptx`, 50 MB max) in the capability settings.

## Upgrade

Deploy Fred normally. The image now also contains `matplotlib`, used to render
charts and backgrounds that have no native PowerPoint equivalent.

## Validation

Enable PPTX Generator for a team, select it on an agent, and ask for a short
deck with a table and a bar chart. Verify the preview pane shows the PDF and
that the `.pptx` download opens in PowerPoint or LibreOffice Impress with an
editable chart.

## Rollback

Use the normal rollback procedure. Deselect the capability on agents first;
decks already generated stay downloadable from the session workspace. No data
migration is introduced.

## Limitations

A deck is capped at 50 slides and regenerated wholesale on each call. When the
PDF conversion fails, the user still gets the `.pptx` download, without a
preview. Known layout gaps are listed in the capability README.
