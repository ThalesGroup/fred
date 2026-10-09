## Why

PPT Filler currently recognizes only `{{key}}`, using separate patterns for slide markers and note headers. Authors need `{key}` and `{{key}}` to work interchangeably, with help that states the exact supported syntax. Tracked in [#3020](https://github.com/ThalesGroup/fred/issues/3020).

## What Changes

- Accept single and double brace markers for text and image keys, including mixed syntax between slide content and note headers.
- Share recognition rules across analysis, note headers, text replacement, and image-anchor discovery.
- Avoid partial matches inside unbalanced, nested, empty, or triple-brace sequences.
- Update English and French help and the package README with both forms and their limits.
- Preserve valid double-brace templates, key identity, metadata, generated JSON, and presenter-note handling.

## Capabilities

### New Capabilities

- `ppt-filler`: Template marker syntax and agreement between analysis, filling, and author guidance. No existing main spec covers this syntax; the active template-download change covers retrieval only.

### Modified Capabilities

None.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/`: shared traversal, notes parser, existing parser/image/fill/formatting tests, and README.
- `apps/frontend/public/ppt-filler-help.md` and `ppt-filler-help.fr.md`: author-facing help, with no new UI component or API shape.
- One migration note with operational impact `none`; no schema migration, dependency, or configuration change.
