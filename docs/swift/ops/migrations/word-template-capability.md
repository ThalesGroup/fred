---
schema: 1
title: "New word_template capability fills and writes any Word template from chat"
impact: minor
configuration: production
configuration_reason: "The Fred chart enables shared word_template preparation with four concurrent activities per worker. Knowledge Flow's packaged chat model uses a supported provider alias. Custom deployments must connect the worker to Control Plane and Knowledge Flow."
---

## Applicability

Existing Fred deployments running the fred-agents pod. The new package
`fred-capability-word-template` is installed in the fred-agents image and
registers the `word_template` capability by entry point.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. The PDF
preview uses the LibreOffice binary already shipped in the fred-agents image
(fred-core's `convert_office_bytes_to_pdf`, as the PPT-filler and
writable-document previews do).

## Configuration

The Fred chart values enable `word_template` in
`preparation.enabled_capabilities` and set its activity concurrency to four
per worker. Custom deployments must enable the capability in their preparation
worker configuration and provide the existing Control Plane and Knowledge Flow
service connections. Knowledge Flow uses its configured chat text model for
template analysis. Both text and vision preparation endpoints authorize the
worker through Knowledge Flow's `preparation_worker_client_id`, which matches
the worker's M2M client ID. The bundled Knowledge Flow model configuration uses
`mistral-medium-2508`. The `configuration_prod.yaml` files are for local Docker
Compose and are not production deployment inputs. No new secret is required.

## Upgrade

Deploy Fred normally, with the fred-agents migration step enabled as for the
writable-document capability. The standard chart rollout needs no additional
operator action. `python -m fred_runtime migrate` discovers the
new tree and creates its own version table
`cap_word_template_alembic_version`, then applies one revision
(`w7t4d5e6f7a8`). It creates five empty tables: `cap_word_template_sessions`,
`cap_word_template_batches`, `cap_word_template_analyses`,
`cap_word_template_snapshots` and `cap_word_template_images`. The session table keeps the selected platform
template's original bytes so an existing document survives library replacement.
No table outside the capability is changed. Existing documents need no
re-ingestion.

Optional activation: an editor enables the capability on an agent and adds its
Word template library. Existing agents stay unchanged until then.

The Control Plane accepts up to eight Word templates in one agent or platform
library. Each original gets one Temporal activity, with at most four analyses
running concurrently per worker. The platform settings drawer can prepare a
replacement library while the current one stays active. Saved templates are
analysed through Knowledge Flow's internal text completion endpoint before the
agent becomes available. Chat documents remain in the ordinary retrieval path.

New API surface, additive only, under `/capabilities/word_template`: session
state, editable content, edits and undo, `.docx` download, PDF preview, the
upload and display of images
(`POST /sessions/{id}/images`, PNG, JPEG or GIF up to 10 MB;
`GET /sessions/{id}/images/{image_id}`). Every route requires the caller to
own the session. An edit that removes content asks the collaborator for
approval through the platform's approval card, even when operator tool approval
is disabled.

## Validation

Before deploying, `make db-check-combined-heads` at the repository root (or
`alembic heads` in `libs/capabilities/fred-capability-word-template`) reports a
single head, `w7t4d5e6f7a8`, for the word_template tree. After the upgrade,
`cap_word_template_alembic_version` holds `w7t4d5e6f7a8` and the agent form lists the "word_template" capability. On an agent with a
template, ask for a document: the side panel shows the filled document as PDF
and the download returns a `.docx`.

## Rollback

Use the normal rollback procedure. Downgrading the tree to base drops the five
tables and their session documents, edit logs and images. An
older release ignores the tables if they are left in place; agents that enabled the
capability then report it as unavailable until it is installed again.

## Limitations

Images and document snapshots are stored in the database. Saved library
templates are prepared before use. Word files attached in the chat remain
ordinary searchable sources when the agent has the document-access capability
with its attachments source enabled.
