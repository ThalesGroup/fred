## Why

Long deliverable arguments are composed before the publication tool appears. A short preparation call marks the start of the workflow in the ordinary tool trace.

Tracking: https://github.com/ThalesGroup/fred/issues/3021

## What Changes

- Add `prepare_document_content(title)`, `prepare_presentation_content(title)`, and `prepare_html_content(title)` to their respective capabilities.
- Instruct the agent to call preparation alone before composing the publication arguments in a later model round, including revisions.
- Use the existing tool trace and completion behavior without frontend changes.
- Keep direct publication, revision identifiers, output parts, validation, and existing deliverable contracts.

## Capabilities

### New Capabilities

None. This follow-up refines the already synced `deliverable-generation` capability in the same draft PR.

### Modified Capabilities

- `deliverable-generation`: Preparation tool scope and its separate-round instruction.

## Impact

The three capability packages provide preparation tools and instruction changes. Capability tests cover the resulting behavior. The normal deployment has no data migration or new setting.

## Non-goals

There is no special pulse during the later model round. The preparation call is short and completes before that round, so it does not provide continuous progress throughout composition. No nested model call, progressive payload, or new runtime event is added.
