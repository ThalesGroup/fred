# PPT Filler Toolkit — Inline Text Formatting — PRD / RFC

Status: Draft
Provider key: `ppt_filler` (extends the existing toolkit)
Area: Agentic Backend (shared inline-markdown parser, fill-tool text traversal) + writable-documents docx export (refactor to consume the shared parser)
Extends: [`PPT-FILLER-TOOLKIT-RFC.md`](./PPT-FILLER-TOOLKIT-RFC.md)

---

## Problem Statement

When the PPT Filler toolkit fills a `{{key}}` text placeholder, the value is inserted as a single
flat string: the substituted run keeps the placeholder run's formatting, but the agent has **no way
to emphasize part of the value**. A filled value cannot say "make this phrase bold" or "italicize
this term" — the whole value renders in one style. Real deliverables routinely need that emphasis:
a bolded key figure in a sentence, an italicized product name, a bolded label inside a longer line.

Today the agent's only options are all-or-nothing (the author styles the entire placeholder) or
nothing at all. There is no per-span control, so the agent cannot produce the lightly-formatted prose
a human would naturally write.

Separately, the writable-documents **Word (`.docx`) export already solves exactly this** — it parses
`**bold**` / `*italic*` from agent-emitted Markdown into styled runs
([`docx_export.py`](../../agentic-backend/agentic_backend/core/writable_documents/docx_export.py)).
That logic is written and tested, but it is welded to python-docx objects, so the PPT Filler cannot
reuse it. Re-implementing the same Markdown subset a second time for pptx would duplicate the parsing
rules and let the two interpretations drift.

## Solution

Let the agent use **inline Markdown** in any text value it passes to the fill tool — limited to the
subset already supported by the Word export: `**bold**`, `*italic*` / `_italic_`, and `***both***`.
When filling a text placeholder, that markup is parsed into styled spans and written as one pptx run
per span, **overlaying** bold/italic on top of the placeholder run's existing formatting (size, color,
font, etc. are inherited from the author's `{{key}}` run, unchanged). A value with no markup produces
exactly one run, identical to today's behavior — so the change is backward compatible.

To stay DRY, the Markdown-subset parsing is **extracted once** into a format-agnostic helper that
returns styled spans, and is then consumed by **both** the existing docx export and the new pptx
fill path. There is a single source of truth for "what our inline Markdown means"; each document
library only owns the thin step of writing those spans as its own runs.

Crucially, the filler parses markup **only in the substituted value**, never in the surrounding
template text — an author's literal `*` in static slide text must never be reinterpreted as emphasis.

## User Stories

### Using the agent (chat time)

1. As an end user, I want the agent to **emphasize part of a filled value** (a key figure, a term,
   a label) with bold or italic, so that the filled slide reads like human-written prose instead of
   one flat style.
2. As an end user, I want emphasis to use familiar **Markdown** (`**bold**`, `*italic*`), so that the
   agent produces it reliably without a bespoke syntax it might get wrong.
3. As an end user, I want a value with **no markup** to look exactly as it does today, so that
   existing templates and behavior are unaffected.

### Authoring (template author)

4. As a template author, I want emphasis the agent adds to **inherit my placeholder's styling** (the
   font, size, and color I set on the `{{key}}` run), with only bold/italic toggled, so that agent
   emphasis never overrides my visual design.
5. As a template author, I want **literal `*` or `_` characters in my static slide text** to stay
   literal, so that punctuation in my template is never mistaken for formatting.

### Maintainability (shared logic)

6. As a maintainer, I want the inline-Markdown parsing to live in **one place** shared by the docx
   export and the PPT filler, so that the two can never diverge on what `**bold**` means and the
   subset is defined and tested once.

## Implementation Decisions

This feature extends the existing `ppt_filler` toolkit (no new provider) and refactors the existing
writable-documents docx export to consume a shared helper. No schema, params, endpoint, or frontend
change is required — markup lives entirely inside the values the agent already passes.

### Supported subset (intentionally minimal)

- Exactly the subset the docx export already supports: **`**bold**`**, **`*italic*`** /
  **`_italic_`**, and **`***both***`**. No underline, color, size, or font — Markdown has no
  standard notation for those and they would require a bespoke syntax with no validation feedback
  loop (deliberately Out of Scope below).
- The inline-code (`` `code` ``) span the docx export recognizes is **not** applied as a style in the
  pptx filler (it maps to a Courier font swap in docx, which is outside this feature's bold/italic
  scope). The shared parser may still surface it; the pptx writer treats such a span as plain text.

### Shared parser (the DRY seam)

- Extract the docx export's `_INLINE_RE`, `_STRAY_MARKER_RE`, and marker-stripping into a
  **format-agnostic** function in a neutral module, e.g.
  `core/markdown/inline.py::parse_inline_markdown(text) -> list[Span]`, where a `Span` carries the
  text plus `bold` / `italic` (and `code`) flags. Pure, no docx/pptx import, fully unit-testable.
- The existing `_add_inline_runs` in the docx export is **rewritten as a thin consumer**: iterate the
  spans and `paragraph.add_run(span.text)` setting `.bold` / `.italic` (and the Courier font for a
  code span). Behavior is unchanged; the existing docx export tests pin that and now also guard the
  shared parser.
- The flat (non-recursive) parsing semantics and stray-marker stripping are preserved exactly as the
  docx export defines them — this RFC moves the logic, it does not change the grammar.

### Fill-tool text traversal (the pptx consumer)

- The change is confined to the shared text traversal's replace step
  ([`traversal.py` `replace_keys_on_slide`](../../agentic-backend/agentic_backend/integrations/ppt_filler/traversal.py)),
  the single spot that today collapses a paragraph onto its first run
  (`runs[0].text = replaced; rest cleared`).
- Markup is parsed from the **substituted value only**, not from the merged paragraph text, so static
  template text containing literal `*` / `_` is never reinterpreted. The substitution boundary is the
  one place the pptx caller genuinely differs from the docx caller (where the whole line is agent
  Markdown) — which is exactly why the shared piece is the **parser**, not `_add_inline_runs`.
- The first run is kept as the **base style source**; each parsed span becomes a pptx run that copies
  the base run's font (size, color, name, …) and **overlays** `bold` / `italic`. python-pptx has no
  public font-copy, so the base font properties are copied explicitly onto each new run.
- A value with no markup yields a single span → a single run → today's exact behavior. Image keys are
  untouched: their `{{key}}` text is preserved for the image pass and never reaches span-writing in a
  way that matters.

### Agent guidance

- One line in the text-key leaf description builder
  ([`toolkit.py`](../../agentic-backend/agentic_backend/integrations/ppt_filler/toolkit.py), the
  non-image branch) tells the agent it may use `**bold**` / `*italic*` in text values. No other
  prompt or tool-description surface changes.

## Testing Decisions

Tests assert **external behavior** and stay offline/fixture-driven, matching the existing
`ppt_filler` and docx-export suites.

1. **Shared parser seam (new, pure)** — `parse_inline_markdown(text) -> spans`: bold, italic (both
   marker styles), bold+italic, plain text, stray/mismatched markers stripped, literal text with no
   markup → single span. This is where the grammar is pinned.
2. **docx export (reused, unchanged assertions)** — the existing
   `test_writable_document_docx_export.py` cases (`.bold` / `.italic` runs, nested emphasis, table
   cells) must still pass after the refactor, now exercising the shared parser through the docx
   consumer.
3. **pptx fill (new)** — fill a fixture template whose `{{key}}` value contains `**bold**` / `*italic*`
   and assert the resulting paragraph has the expected runs with the right `bold` / `italic` flags and
   that the **base font is inherited** (size/color/name unchanged from the placeholder run). A value
   with no markup yields a single unchanged run. A template with a **literal `*`** in static text is
   left untouched. The existing parse → fill → re-parse round-trip guard still holds (markup affects
   values, not key detection).

## Out of Scope

- Underline, strikethrough, font color, font size, and font family — no standard Markdown notation;
  they would need a bespoke syntax with no validation feedback loop. Revisit only if a concrete need
  appears.
- Block-level Markdown (headings, lists, tables) inside a value — placeholders are inline spans, not
  documents; block constructs belong to the docx export, not the filler.
- Markdown in **static template text** — only agent-provided values are parsed, by design.
- Markdown in **image** key values (they carry a document id, not prose).
- Any change to schema, params, analyze/save endpoints, or the frontend.

## Further Notes

- **Why a refactor and not a copy:** duplicating the Markdown subset for pptx would let the docx and
  pptx interpretations of `**bold**` drift. Extracting the parser makes the subset a single tested
  unit; the docx side gets *safer* (its parsing is now covered as a shared unit) as a side effect.
- **Highest-risk watch-points:**
  1. The value-vs-literal boundary — parsing the substituted value only. Get this wrong and an
     author's literal `*` in static text becomes spurious emphasis. Pinned by the literal-`*` test.
  2. Explicit base-font copy onto each new pptx run — python-pptx has no public copy, so missing a
     property (size/color/name) would silently drop the author's styling on emphasized spans. Pinned
     by the base-font-inherited assertion.
- **Backward compatibility:** a markup-free value produces one run exactly as today, so no existing
  template, saved agent, or test changes behavior.
