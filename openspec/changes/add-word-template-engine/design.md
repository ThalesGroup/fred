# Design - Fill and write any Word template from an agent conversation

## Context

See `proposal.md` - Why. This design records the decisions a reviewer needs
and the facts that shaped them; the document-map format is in `docmap.py`.

Facts observed in live use, before the guards existed:

- A model rebuilt a table-only form in its own layout by removing every copy
  of a project block and writing Markdown tables.
- Models wrote over template headings (turning them into bold body text),
  added up to 42 sub-section headings to one document, and rewrote the
  template's fixed RGPD clauses.
- A model wrote a whole specification in one turn, and hit the runtime's
  12-calls-per-turn limit (`fred_agents/tool_pacing.py`) mid-document.
- The runtime turns any error tool result into a generic sentence shown as
  the final answer (RUNTIME-EXECUTION-CONTRACT §8.74), so a refusal returned
  as an error was invisible to both the model and the collaborator.

## Goals

**Goals:**

- Any Word template works unchanged; no template-specific code.
- The collaborator decides the document's structure and reviews each part.
- Rules that protect the document hold whatever model is configured.

## Decisions

### 1. A generic engine; use cases in the agent prompt

The engine exposes the document and a small set of operations; it never
recognises a kind of document. A specification agent and a weekly-report
agent share the engine and differ by their prompt. Rejected: one mechanism per
kind of template (marked guidance, unmarked chapters, placeholders, forms),
which does not generalise.

### 2. Positional addresses with guards, not stable ids

Addresses are positional and shift after structural edits. Instead of stable
ids (a larger change), the engine refuses edits made on an outdated read: read
before edit, re-read after a structural edit or undo, stale-read refusal after
a collaborator edit. Detection reads the turn's own tool results (pod-local,
no shared state), so it holds across replicas.

### 3. Rules in code where a prompt was not enough

Each guard exists because a prompt rule was observed being ignored. Guards
apply to the model's batches only; the collaborator's edits (Rédaction view)
are never limited. A guard refuses with an actionable message rather than
silently changing the batch.

### 4. The collaborator decides the structure, through the approval gate

Removing content, adding a heading and changing fixed wording are not
forbidden: they go through the existing platform approval gate (`HitlSpec`).
The gate's question is fixed text (the SDK carries no per-call text), so it
points to the agent's message, which the engine's principles require to state
exactly what will change. Fixed-wording changes need an explicit
`changes_template` flag because detecting them needs the document state, which
the synchronous gate predicate cannot read; the asynchronous tool-call guard
refuses an undeclared change and tells the model how to ask.

### 5. One part of written content per turn

Writing a whole document in one turn both bypasses the collaborator's review
and runs into the runtime's tool-call limit. The engine limits written body
content to one part per turn; filling cells and fields stays free, so form
templates (weekly reports) fill in one turn. Parts already written in the turn
are read from the applied batches' replies (`Part N now:`); part ids are
heading-based and stable unless headings are added or removed.

### 6. Refusals are plain results

Returning refusals as errors made them invisible (decision context, §8.74).
Refusals the model must act on are plain results; real failures (no session,
unavailable document) stay errors.

### 7. Progress computed from the document

The model forgets that a batch was refused or never ran, and claims a part is
done when it wrote something in it. A per-part list ("part 2 still to write")
in the prompt was ignored in three live conversations out of three: once the
model has written in a part, the list no longer tells it what is missing.

So each applied model batch is followed by a **check of the parts it
touched**, added to the batch's reply, where the model reads it before
answering: each place still holding template text, located in plain words
(nearest heading, or the cell's row label) and by its current address, plus
the [À COMPLÉTER] markers left. Every model call carries the same check for
the whole document as a count per part, which doubles as the final review.

- **Template text** is the base's guidance and placeholders: analysis roles
  `replace`/`fill`, body paragraphs coloured whole, and generic placeholder
  patterns (bracketed fields, "XXX", lorem ipsum, zero-filled dates and
  numbers), so the check does not rest on the analysis alone. TOC lines and
  fields are left out: coloured TOC lines would otherwise be reported in
  every such template on every edit.
- **Texts, not addresses**: the check finds the base's texts in the current
  document, so it follows removals, insertions and repeats; parts are named
  by title because their numbers shift.
- **Fixed wording is not re-checked**: the fixed-wording guard already
  refuses changes; a fixed paragraph holding a field is reported as a detail
  to fill with `replace_text`, so the model is not sent into that guard.
- **Informative, not blocking**, and no model call.

Cached per document bytes; computed in a worker thread.

### 8. An attached file is a source by default

Collaborators attach needs documents "to write from"; making them the base
rewrote the needs document instead of producing the requested one. The base is
the document to deliver; sources stay sources.

### 9. Prepare the saved library outside turns

Declare `PreparationSpec` and implement `prepare()` as PPT Builder does. The
control plane owns immutable originals and a revision-fenced result; the worker
reads each library asset, calls Knowledge Flow's bounded internal text endpoint,
and writes the original and analysis under the attempt prefix. The result maps
sha256 to the analysis. A turn reads only its bound preparation result. An empty
library has no preparation. Session attachments continue their first-use path.

The shared workflow schedules one Temporal analysis activity per original, up
to four concurrently per preparation. The worker also caps Word analysis at
four concurrent activities per replica. Each activity calls `prepare()` with
one asset and writes a distinct artifact; a final activity combines the
analyses and publishes the revision-fenced result. A failed activity retries
the whole attempt without publishing partial results. Both agent and platform
libraries contain at most eight templates and 64 MiB of originals.

The editor uploads only new files. The preparation admission therefore retains
the previous slot's assets by the ordered sha256 list returned by Word's save
validation, adds new uploads, and discards removed entries. It rejects any hash
not backed by an existing or new asset. Label-only edits reuse the current
preparation. Copy/export carry the selected originals to the new owner.

Saving an agent library validates new Word files in a bounded group of four.
When a session selects a platform template, the capability stores that base
with the session before reporting the selection. Document routes read the
session's saved base, so a later platform replacement cannot change an
existing document. Prepared analysis is also cached in the shared Word store
for the editable content route.

Knowledge Flow serves text analysis through a service-only route, using the
same worker identity, bounded concurrency, timeout and response checks as the
vision route. It uses its configured text model; no agent turn or pod-local
background job performs library analysis. Generic preparation status and retry
drive the editor's progress and recovery controls.
The text client retries a bounded number of 429 capacity responses with jitter
inside each asset activity, so overlapping worker replicas do not restart a
whole library for a short Knowledge Flow queue.

Session mutations lock the same SQL session row before checking batch count or
selected base. This serializes selection, append, undo and attachment or image
removal across pods. Removing an agent's final template retires its preparation
so the platform default can apply. Image preview URLs are revoked when the
conversation pane closes or switches sessions.

The platform settings drawer exposes a default Word library through the
same active/candidate preparation flow as PPT Builder. One candidate can hold
multiple files in the declared slot. Uploading a replacement library keeps
the active result until the candidate succeeds. An agent with its own library
uses that library; an agent without one uses the platform result when
available. The platform result carries ordered template hashes and labels to
the turn through preparation settings. The settings text uses the configured
site name and agent nickname instead of a product name.

When an agent has no library of its own, its form reads the active platform
library and displays those templates with the shared list in read-only mode.
Adding a personal template replaces that inherited list in the form.
Both agent-form states use the same name-only rows and scroll limit; personal
rows add the edit and delete controls.

The settings card lists active templates in a scrollable list capped at two and
a half rows, with the platform's edit and delete icon buttons on each row.
Names can be edited inline; they help agents choose a template and do not
rename the original file. Removals, additions and renames stay in a local
draft until one Save. The existing
platform candidate route accepts IDs of retained active assets followed by new
uploads, plus the active preparation ID observed by the editor. Under the
selection row lock, control-plane verifies those IDs belong to that active
preparation, applies count and byte limits to the full set, and links retained
immutable assets to the new candidate. Existing cleanup already retains assets
referenced by current or uncleaned preparations. The worker still receives one
preparation with one activity per template, bounded by its current concurrency
limit. A stale editor receives a conflict and reloads the current selection.
The agent form uses the same library card and row controls. Name, file and
removal edits update only the form's local state; its outer Save persists them.
The platform card names its active library and its
candidate separately so removed files remain visibly current only until the
candidate succeeds. The editor has no deleted-file history. A conversation
that already selected a platform base keeps its stored original; one without
a selection reads the then-active library on its next turn.

## Migration Plan

New package and tables only (`cap_word_template_*`, own version table). Existing
library entries without saved hashes require re-upload to enter preparation.
Rollback: remove the capability from the agents; the tables can stay.
