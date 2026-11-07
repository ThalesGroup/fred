---
schema: 1
title: "Guide exact document references and remove NUL from document writes"
impact: none
configuration: none
configuration_reason: "Only tool guidance, writable-document text cleaning and history serialization change; no configuration key or default changes."
no_action_reason: "Installations are fresh and no schema, stored format, contract or field name changes, so there is nothing to rename or migrate."
---
## Applicability

Fresh Fred installations using native document reading, summarization or writable documents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Call a writable-document tool with a title or Markdown containing U+0000: the save succeeds, the saved text no longer contains the character, and the tool result announces how many were removed. Reload the conversation: the tool call and its result stay paired, and the stored call arguments show `[U+0000]` where the character was. Search hits still expose `uid`, which remains the value to copy into the `document_uid` argument of the reading and summary tools.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The tool guidance does not guarantee model behavior. History marks U+0000 in text values only; JSON object keys are not rewritten. Valid Unicode and literal marker text stay intact.
