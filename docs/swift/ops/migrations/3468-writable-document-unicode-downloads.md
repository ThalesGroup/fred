---
schema: 1
title: "Fix writable-document downloads with Unicode titles"
impact: none
configuration: none
configuration_reason: "Only export filename header encoding changes; no configuration keys or defaults change."
no_action_reason: "Existing documents and permissions are unchanged; Unicode downloads work after normal deployment."
---
## Applicability

Fred deployments using the writable_document capability.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Export a writable document titled `Örnek Ürün Yapısı` as Word and Markdown.
Both downloads should succeed with readable document content. The HTTP response
uses a UTF-8 percent-encoded `filename*`; ASCII filenames retain quoted `filename`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Rolling back restores the download failure for titles containing characters
outside Latin-1.

## Limitations

Existing filename sanitization still applies. No additional migration limitations
are introduced.
