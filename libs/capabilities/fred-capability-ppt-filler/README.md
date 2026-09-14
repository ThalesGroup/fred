# fred-capability-ppt-filler

Fred agent capability that fills an uploaded PowerPoint template from chat.

An author uploads a `.pptx` whose slides carry `{key}` or `{{key}}` placeholders and whose
slide notes describe each key (a `{key}:` or `{{key}}:` header plus prose, optional
`- type: image` / `- folder: ...` metadata for picture keys). The capability
parses and validates the template, then gives the agent a fill tool that
substitutes the keys - honoring inline Markdown (`**bold**` / `*italic*`) in the
substituted values - and produces a downloadable, filled deck.

This package holds the pure, offline core: the template parser/validator, the
shared text-frame traversal (list + replace), the image-anchor geometry seam, and
the folder-resolution / image-location validation layer.

## Template markers

Single and double braces identify the same case-sensitive key. Mix either form
between slides and notes, including multi-key headers such as `{first}, {{last}}:`
and image markers. Leading/trailing key whitespace is ignored. The single-brace
form requires at least one character and no braces inside the key. Double-brace recognition retains its legacy rule: the key is everything
up to the first closing brace, followed by two closing braces. No extra syntax
validation is introduced for existing templates.

Markers split across runs in one paragraph are supported in text boxes, table
text, and grouped shapes. Images use the containing shape's placement box;
table cells remain invalid image locations. Chart text and SmartArt are unsupported.

## `ppt_builder` (same package)

A second capability, `ppt_builder` (`fred_capability_ppt_filler/builder/`),
generates a deck from a chat plan on an _unannotated_ corporate template — or
on a built-in theme when the agent has none. The template is analysed at save
time into a pattern inventory (master layouts by placeholder type, example
slides by placeholders, sample-text lexicon, geometry and repeated groups);
the author can correct it in the agent form; the agent's `build_presentation`
tool renders a typed plan by instantiating layouts or duplicating example
slides and filling their zones by role. Delivery reuses the filler's preview
part and pane. Design: `openspec/changes/ppt-builder-capability/`, issue #2679.

Optional annotation channels the analysis honours: a shape name from the
Selection pane (`title`, `body`, `number`, `keep`, `heading_2`…), and
`intent:` / `label:` lines in a slide's speaker notes.

## Spec

The current template contract is in
[`openspec/specs/ppt-filler/spec.md`](../../../openspec/specs/ppt-filler/spec.md).
Author help: [English](../../../apps/frontend/public/ppt-filler-help.md) and
[French](../../../apps/frontend/public/ppt-filler-help.fr.md).

## Registration

Installing this package _is_ the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml` (`ppt_filler = "fred_capability_ppt_filler.capability:PptFillerCapability"`).

## Validation memory and admission

Selection and save each independently open the deck once. One marker walk supplies
field discovery and table-cell image checks, without allocating image anchors or
computing coordinates. Generation retains its geometry path. Only the schema survives
into asynchronous folder lookup; worker cleanup collects cyclic presentation objects
after validation and generation,
including failed processing. Collection runs in the worker but can pause other Python
threads while holding the GIL. The existing per-pod limit remains four heavy jobs with
fail-fast busy feedback. This count is not a memory budget: four large decks can still
exceed a deployment's limit, and cancelling an awaiting request can release its slot
before its worker stops.

Save transport failures distinguish an unreachable runtime (503), operation timeout
(504), and interrupted communication (502). The form translates their stable codes;
transport logs include exception type and duration with the current request context,
without service URLs or raw exception messages. A dropped connection does not identify
an OOM kill or require Kubernetes access.
