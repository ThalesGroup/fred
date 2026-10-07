---
schema: 1
title: "Retire general-purpose personal, team-shared, and agent file areas"
impact: major
configuration: production
configuration_reason: "The enableAllResourceSpaces frontend flag and the general-purpose resource tabs are removed."
---

## Applicability

Deployments that use the former `Mon espace`, team-shared, or agent-files UI, or call the general-purpose Knowledge Flow `/fs` and SDK interfaces.

## Prerequisites

Export any files in the retired personal or team-shared areas that must remain accessible. Their stored bytes are not deleted or migrated. Inventory external/live ReAct definitions for the retired `artifacts.publish_text` and `resources.fetch_text` tool references and migrate any matches. The separate `fred-samples/apps/document-triage` sample still uses `teams/{team}/shared/triage`; migrate or decommission it before running it against this version.

## Configuration

Remove `enableAllResourceSpaces` from private control-plane and worker Helm overlays. The bundled chart and generated configuration schemas no longer accept it.

## Upgrade

Deploy the frontend, Knowledge Flow, SDK, runtime, and chart together. Team Resources now presents the corpus workspace only. Knowledge Flow rejects `/teams/{team}/users` and `/teams/{team}/shared` before storage access. Generic agent file reading, listing, text publishing, and sharing interfaces in the UI and SDK are retired. HTTP `/fs` read routes remain for the virtual corpus view and can still resolve technical agent paths; authenticated `/fs/upload`, `/fs/download`, and `/fs/delete` remain for PPT Filler configuration assets and outputs. The document APIs remain available.

## Validation

Confirm the Resources page has no personal, team-shared, or agent-files tabs; retired paths are rejected; `list_document_tree` works; and a saved PPT Filler template still produces a downloadable presentation. Check that the frontend bootstrap no longer exposes `enableAllResourceSpaces`.

## Rollback

Roll back the paired code and chart together to restore the former interfaces. No object-store migration or deletion is performed.

## Limitations

This change does not decide when to delete retained objects in retired areas. No deployed-environment inventory of external agent definitions or end-to-end ReAct PPT Filler run is included.
