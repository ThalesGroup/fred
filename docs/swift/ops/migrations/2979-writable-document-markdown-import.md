---
schema: 1
title: "Keep literal comparisons in the writable-document rich-text editor"
impact: none
configuration: none
configuration_reason: "Only frontend document rendering changes; no configuration keys or defaults change."
no_action_reason: "Existing documents, APIs and exports are unchanged; Markdown preparation takes effect with normal frontend deployment."
---

## Applicability

Existing Fred deployments using the writable-document capability.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing documents require no migration or regeneration.

## Validation

Open a writable document containing `Minimal overhead (<3ms for dense retrieval).`.
Check that the formatted document appears in the rich-text editor with the literal
`<3ms` visible. Opening it must not save a new version. Edits must still be saved,
and Word and Markdown downloads must remain available.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
The previous frontend can again show an empty editor for incompatible Markdown.

## Limitations

The sanitizer adapts literal text and autolinks for MDX import. It does not add
support for arbitrary JSX components or unsupported Markdown constructs.
