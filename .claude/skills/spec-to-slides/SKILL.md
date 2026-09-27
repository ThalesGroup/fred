---
name: spec-to-slides
description: Turn a spec, RFC, or OpenSpec change into a technical slide deck for the dev team — agenda first, a context section before any code, concrete code-level changes per sub-project (impact map, touch maps, before/after, generated flow and sequence diagrams), implications, and 2-3 implementation-slicing proposals with pros/cons. Output is an ad hoc HTML deck (Artifact or temp file), never committed.
user-invocable: true
argument-hint: "<path to RFC / spec / openspec change dir> [--lang fr|en] [--duration 30m] [--audience backend|frontend|full-stack]"
---

# Spec → Technical Slides

Produce a deck that lets a developer who has **not** read the spec understand
what will change in the code, in which sub-projects, why, and how to cut the
work. It is a bridge between the document and the codebase, not a summary.

## What the deck must do

1. **Agenda first**, section dividers, a progress bar on every slide.
2. **Context before code**: vocabulary (≤ 4 terms), the situation today as a
   person or the model sees it (real text from the repo), ≤ 3 numbers.
3. **Code-grounded changes**: an impact map of the whole monorepo, then one
   touch map per touched sub-project, a before/after panel wherever the change
   is visible to someone, one sequence per changed runtime flow.
4. **Implications**: compatibility, contracts, migration, security,
   observability, and where the spec and today's code disagree.
5. **Slicing**: two or three ways to cut the work, each with a generated
   dependency diagram and pros/cons, a comparison table, one recommendation
   with the first issue title, the open questions.

## Rules that matter

- **Never commit the deck**; write it to the scratchpad, publish as an
  Artifact when available, or hand over the path. Read-only on the repo.
- **Do not invent**: what the spec does not say is marked "not specified";
  where spec and code diverge, the code and the frozen contract docs win and
  the divergence gets its own row.
- **Use the frame, don't write layout CSS.** Copy `references/deck-frame.html`
  verbatim at the top of the deck and write slides with the patterns in
  `references/patterns.md`. Do not add your own CSS beyond overriding tokens in
  `:root` (fonts, hues). The frame keeps every block at its content height,
  centres the body, and scales down a slide that is slightly too full instead
  of clipping it.
- **One message per slide.** Sentence title ≤ 14 words, no code in it; a
  one-line lede saying what the reader looks at and why; one main block,
  optionally a second block that explains the first. Nothing decorative.
- **Real content, readable.** Text ≥ 15 px in tables and panels, ≥ 14 px in
  diagrams; cells ≤ 10 words; panels ≤ 12 lines of real repo text; a card
  carries 2–4 lines, not a paragraph.
- **Every path names its sub-project first** with a chip (`c1…c8`, one hue
  per sub-project, stable across the deck). The impact map shows every
  sub-project, touched or not.
- **Diagrams are generated** by `scripts/diagram.py` from a JSON spec (nodes +
  explicit edges, or participants + steps). Never draw boxes and arrows by
  hand. Every diagram has a caption written for someone who has not read the
  spec; the legend is generated.
- **A table or a diagram never sits alone.** Every table gets a takeaway
  under it (its conclusion) and, with fewer than 7 rows, a `.notes` context
  column beside it (why it matters, how to read it, what to do). Appendix
  slides use normal type, ≤ 6 rows, with the same lede and notes — a small
  table floating in an empty frame is a bug.
- **Fewer, fuller slides.** Merge two thin slides; a table may reach 8 rows,
  a touch map 8 cards. But nothing scrolls and nothing is clipped: the check
  below must report zero clipped slides and no slide scaled under 0.85.
- **Appendix** for full paths, line numbers and sources: dense tables, split
  across slides.

## Inputs

`$ARGUMENTS`: the source (RFC in `docs/swift/rfc/`, an OpenSpec change dir,
a PR/issue number, or any markdown file) and optional `--lang` (default: the
language of the request), `--duration` (caps the slide count at ≈ 1.5 min per
presented slide), `--audience` (`backend` folds frontend detail into one
slide, and vice versa). No source → ask for it and stop.

## Workflow

**1. Read and size.** Read the whole spec. Score it with
`references/complexity-rubric.md`; the tier gives the budget of presented
slides. Print the line `Tier … (score n/24) Budget … Talk …` in the reply.

**2. Ground in the code.** For every component the spec names: locate it
(`grep -rln`), read enough to state its current shape in one sentence, check
the frozen contracts (`docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`,
`CONTROL-PLANE-PRODUCT-CONTRACT.md`), the work in flight (`gh issue list
--search`, `openspec/changes/`), the Alembic head if a table changes. Collect
one concrete before/after example per visible change (the YAML, the prompt,
the screen). Build the touchpoint table: sub-project (chip) → file → today →
after → new/modified/removed. Assign chips here.

**3. Outline.** Title, agenda, then per part the list of sentence titles;
read them alone — they must tell the story. Pick the slicing patterns from
`references/slicing-patterns.md` that genuinely fit.

**4. Build.** Write the JSON specs for every flow and sequence, generate them
with `scripts/diagram.py`, and check each SVG's edges against the spec. Write
`<scratchpad>/spec-to-slides/<slug>.html`: the frame, then the slides.

**5. Check.** `scripts/check-deck.sh <slug>.html` renders the deck headless,
prints every slide whose content is clipped or scaled below 0.85 (with the
element and its size), and writes contact sheets. Look at the sheets once for
half-empty slides, unreadable text, a diagram that does not match its
caption, a path without its chip. Fix, re-run until the check is clean, stop.

**6. Deliver.** Artifact if the tool is available (load `artifact-design`
first, favicon 🎞️), otherwise the path. Reply with: location, the tier line,
presented/appendix counts and talk length, the recommended option in one
sentence, the divergences and open questions to look at first.
