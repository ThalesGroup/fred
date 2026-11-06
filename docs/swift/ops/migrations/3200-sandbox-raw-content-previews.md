---
schema: 1
title: "Sandbox inline raw-content document previews"
impact: none
configuration: none
configuration_reason: "Only two response headers are added to the Knowledge Flow raw-content stream; no configuration keys, defaults or schemas change."
no_action_reason: "Stored documents, APIs and the PDF preview are unchanged; the stream gains Content-Security-Policy: sandbox and X-Content-Type-Options: nosniff with a normal deployment."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Run the admin self-test security family and check that the step "Inline
previews never serve runnable SVG or HTML" passes. Alternatively, request
`GET /knowledge-flow/v1/raw_content/stream/{document_uid}` with a bearer token
and check the response carries `Content-Security-Policy: sandbox` and
`X-Content-Type-Options: nosniff`; a PDF still opens in the document viewer.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A reverse proxy that strips or overrides `Content-Security-Policy` on this
route removes the protection; it does not affect the preview itself.
