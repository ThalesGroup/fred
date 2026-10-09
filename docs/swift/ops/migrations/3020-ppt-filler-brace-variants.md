---
schema: 1
title: "Accept single and double brace PPT Filler markers"
impact: none
configuration: none
configuration_reason: "Only PPT Filler marker recognition and author help change; no configuration keys, chart values, or permissions change."
no_action_reason: "Valid double-brace templates, stored schemas, and tool inputs remain compatible; normal deployment enables single-brace authoring without data migration."
---
## Applicability

Fred deployments using the PPT Filler capability.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing valid `{{key}}` templates continue to work.
Authors can also use `{key}`, including mixed syntax between slides and notes.

## Validation

Analyze a template containing `{name}` and `{{name}}` with a single description
in its slide notes. Fill it and verify both markers become the same value with
no leftover braces. Verify the French and English help describe both forms.

## Rollback

Use the normal rollback procedure. Before filling a template with an older
runtime, change any single-brace markers and note headers back to double braces
and upload the template again. No data migration is introduced.

## Limitations

Existing double-brace recognition, note-header boundaries, and replacement
behavior are unchanged. The additional single-brace syntax requires at least
one character and no braces inside the key. No new validation or error codes
are introduced.
