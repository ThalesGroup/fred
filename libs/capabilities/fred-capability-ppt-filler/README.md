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

## Spec

The current template contract is in
[`openspec/specs/ppt-filler/spec.md`](../../../openspec/specs/ppt-filler/spec.md).
Author help: [English](../../../apps/frontend/public/ppt-filler-help.md) and
[French](../../../apps/frontend/public/ppt-filler-help.fr.md).

## Registration

Installing this package *is* the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml` (`ppt_filler = "fred_capability_ppt_filler.capability:PptFillerCapability"`).

## Validation memory and admission

Selection and save each independently open the deck once for field extraction and
image placement checks. Only the schema survives into asynchronous folder lookup;
worker cleanup collects cyclic presentation objects after validation and generation,
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
