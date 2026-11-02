## Why

The packaged catalog overlaps on visualization and repeats general model advice. Consolidate the developer-reviewed procedures and invocation modes so agents load targeted instructions and users see intentional commands. Tracking: [#3402](https://github.com/ThalesGroup/fred/issues/3402), continuing draft [PR #3342](https://github.com/ThalesGroup/fred/pull/3342) on `codex/platform-skills-evolution`.

## What Changes

- Make `analyze-data`, `compare-options` and `summarize-document` model-only. Condense comparison reminders; keep a minimal summary procedure with conditional guidance for complex or fidelity-sensitive documents.
- Make `meeting-minutes` user-only through the existing invocation controls.
- Merge diagram and numerical visualization guidance under the existing `graph` identity, presented as Visualization/Visualisation and retaining user/model invocation. Move Mermaid syntax/examples into a packaged reference read only for Mermaid output.
- **BREAKING** Remove the separate `data-visualization` and `verify-answer` catalog entries. Former direct selections of removed or newly user-ineligible names are rejected through existing validation.
- Update packaged-content/eligibility tests, localized presentation, affected contract examples and the migration guidance. Retain usable historical skill activity.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: revise the packaged catalog, invocation modes, progressive visualization/summary guidance and examples referring to retired commands.

## Impact

Runtime skill resources and relevant tests; frontend catalog translations and consumer tests; current skill specifications, relevant runtime/chat documentation and the existing branch migration guide. No SDK/API shape, loader, renderer, dependency, table or authorization mechanism is added.

Packaged resources remain immutable startup snapshots. Every runtime replica must receive the updated package. The existing `graph` policy applies to its merged scope; an old `data-visualization` override does not migrate implicitly and must be reviewed before rollout. Old instructions already present in conversation context retain the existing continuity semantics.

## Non-goals

No procedural changes to `analyze-data`, and no changes to `grounded-research` or `grill-me`; no skill aliases, automatic persisted-policy rewriting, instruction editor, new execution tools or renderer implementation. No answer-quality or latency improvement is claimed without measurement. The developer confirmed the scope on 2026-11-02 and explicitly added model-only `analyze-data` during implementation.
