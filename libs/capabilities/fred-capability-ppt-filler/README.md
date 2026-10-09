# fred-capability-ppt-filler

Fred agent capability that fills an uploaded PowerPoint template from chat.

An author uploads a `.pptx` whose slides carry `{{key}}` placeholders and whose
slide notes describe each key (a `{{key}}:` header plus prose, optional
`- type: image` / `- folder: ...` metadata for picture keys). The capability
parses and validates the template, then gives the agent a fill tool that
substitutes the keys — honoring inline Markdown (`**bold**` / `*italic*`) in the
substituted values — and produces a downloadable, filled deck.

After grounding the requested content, the agent calls
`begin_ppt_generation(title)` with a short title, waits for its acknowledgement,
then composes placeholder values and calls `fill_ppt_template` in a later model
round. Preparation reads no assets and writes no workspace file. Both tools are
available only when the configured template enables filling; direct fill calls
and optional image tools remain supported. The live trace shows content
generation between the two calls, followed by PowerPoint rendering. See the
[deliverable generation spec](../../../openspec/specs/deliverable-generation/spec.md).

This package holds the pure, offline core: the template parser/validator, the
shared text-frame traversal (list + replace), the image-anchor geometry seam, and
the folder-resolution / image-location validation layer.

## Spec

The design lives in the Kea RFCs `docs/rfc/PPT-FILLER-*.md` on the old repo, and
the work is tracked in GitHub issue #1903.

## Registration

Installing this package *is* the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml` (`ppt_filler = "fred_capability_ppt_filler.capability:PptFillerCapability"`).
