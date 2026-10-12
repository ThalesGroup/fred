# RFC — PPTX Generator Capability: open questions

**Status:** Shipped (v1). Only the deferred items below remain open.
**Author:** Ewan Schwaller
**Area:** `libs/capabilities/fred-capability-pptx-generator/`, `frontend`

The settled design (why it is separate from `ppt_filler`, tool schema, brand
template handling, layout resolution, guardrails, known gaps) lives in
`libs/capabilities/fred-capability-pptx-generator/README.md`. This RFC keeps only what is
not decided.

## Deferred — not built, no decision yet

1. **Treemap, sankey and network-diagram charts.** They need a new dependency
   (e.g. `squarify`), unlike the current matplotlib fallbacks.
2. **Iterative editing** ("regenerate slide 4 only") instead of whole-deck
   regeneration, and **agent read-back** of a previously generated deck.
   Both likely need an owned table and router to persist decks, the same
   extension path `html_artifact` left open.
3. **Verbatim template-slide reuse** (insert a fixed legal/contact slide
   untouched). Today a reused slide is always filled according to `kind`.
4. **Three-zone chapter dividers** (badge + title + subtitle). The content-based
   zone detection only handles the two-zone case and falls back to type-based
   filling otherwise.
5. **Title/shape overlap.** Fixing it needs real text measurement (font
   metrics or a headless render), a new dependency for a narrow problem.
6. **Generated images.** Only corpus documents can be placed; a text-to-image
   model would be a platform-level decision first.
