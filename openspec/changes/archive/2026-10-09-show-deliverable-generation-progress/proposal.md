## Why

The model composes long document, slide, and HTML payloads before ReAct emits the publication tool call, leaving users without a specific indication of that work. An early preparation call should make composition visible before the existing tool writes or renders the deliverable.

Tracking: https://github.com/ThalesGroup/fred/issues/3021

## What Changes

- Add short `begin_document_generation(title)`, `begin_ppt_generation(title)`, and `begin_html_artifact_generation(title)` tools to the corresponding enabled capabilities.
- Require capability instructions to call preparation separately, wait for its result, then compose and publish with `write_document`, `fill_ppt_template`, or `render_html_artifact`. Apply this sequence to new deliverables and revisions.
- Show localized composition activity between successful preparation and publication while the turn is live, including when the model emits no reasoning text. Keep the actual preparation row completed once its result arrives.
- Retain existing publication arguments, revision identifiers, result parts, validation, and direct invocation behavior.

## Capabilities

### New Capabilities

- `deliverable-generation`: Early preparation, composition visibility, and compatible publication for the three shipped deliverable capabilities. No current spec covers this behavior: capability packs describe agent-form selection, while LLM observability describes operational diagnostics.

### Modified Capabilities

None.

## Impact

The writable-document, PPT-filler, and HTML-artifact packages gain preparation tools and instruction changes. Frontend trace utilities, `ThoughtTrace`, turn-lifecycle wiring if needed, and French/English translations gain composition labels; targeted capability, ReAct event-order, and frontend lifecycle tests cover the change. Package READMEs and `COMPONENT-UX.md` describe the final workflow.

This adds one normal model round per prepared deliverable, with latency and token overhead to assess during implementation. No nested LLM invocation, runtime event type, OpenAPI shape, database migration, or deployment setting is proposed.

## Non-goals

PPT builder, background generation jobs, progressive document contents, percentage progress, and Deep/Graph capability support are outside this slice. Existing `open_writable_document` publication of already-composed workspace content keeps its direct path. Implementation starts after developer confirmation of this proposal and its acceptance criteria.
