# Fill and write configured Word templates in an agent conversation

Tracking: none yet - proposed from a downstream fork for upstream review.

## Why

Many organisations write their documents in imposed Word templates:
specifications, requirement statements, weekly reports. Each template has a
cover page, headers and footers, tables, and guidance telling the author what
to write - sometimes in coloured text, sometimes in plain text, sometimes as a
form made only of tables.

Fred has no capability that fills such a template as it is:

- `writable_document` co-authors a Markdown document and exports it to a blank
  Word file; the organisation's template is not used.
- `ppt_filler` fills a PowerPoint template, but only where an author placed
  `{{key}}` markers by hand; existing templates do not work unchanged.

Live use also showed that prompts alone do not keep a model inside a template:
models rebuilt forms in their own layout, wrote over headings, invented
sub-sections, rewrote fixed clauses and wrote a whole document in one turn.
The engine therefore enforces its key rules in code, and leaves the
document's structure to the collaborator.

## What Changes

- **New capability `word_template`** ("Rédaction sur modèle Word"), a separate
  package `libs/capabilities/fred-capability-word-template`, registered through
  the `fred.capabilities` entry point. It knows no kind of document: use cases
  (a specification, a weekly report) live in each agent's prompt.
- **Document map**: every addressable element of the `.docx` gets a positional
  address (`P12`, `T3.R2.C4`, `H1.P2`, `X1.P1`), read part by part.
- **Template analysis** of the agent's library in the shared capability
  preparation worker after save, using Knowledge Flow's configured text model.
  The worker publishes revision-bound originals and analysis artifacts; the
  agent is preparing until they are ready.
- **Seven operations** applied as one validated batch: `set_text`,
  `replace_text`, `write`, `insert_after`, `repeat`, `remove`, `move`; the document is
  always the base plus an ordered, undoable operation log.
- **Document base**: a template from the agent's library or the active platform
  library. Chat attachments remain information sources through ordinary retrieval.
- **Images** attached in the chat can be
  placed in the document.
- **Rédaction view**: the collaborator reads and edits the document in a side
  panel (chapters as rich text, cells inline, cover page and headers as
  fields), with Duplicate, Remove and Undo; conflicts return 409.
- **Guards in code**, all on the model's batches only (the collaborator's own
  edits are free):
  - one `edit_document` per model step; read before edit; re-read after a
    structural edit or an undo; stale-read refusal after a collaborator edit;
  - the last copy of a template table is kept; template headings are kept;
  - fixed wording is kept unless the change is declared (then approved);
  - written content goes into one part per turn;
  - removals, new headings and declared fixed-wording changes go through the
    platform approval gate, with a plain-language question;
  - refusals the model must act on are plain results, not errors (an error
    result replaces the model's answer with a generic sentence).
- **Progress from the document itself**: after each model batch, a check of
  the parts it touched lists, in plain words and by address, every place
  still holding template guidance or placeholders and the [À COMPLÉTER]
  markers left; each model call carries the same check for the whole
  document as a count per part. Template text includes generic placeholder
  patterns, not only the analysis.
- **HTTP routes** under `/capabilities/word_template/sessions/{session_id}`
  (state, images, content, edits, undo, preview, download), each
  checking that the caller owns the session.
- **Own Alembic tree** (`cap_word_template_*`, one revision), registered in
  the combined migration checks.

## Capabilities

### New Capabilities

- `word-template`: how an agent fills and writes a Word template as it is -
  the document map, the operations, the document base, the guards on the
  model, the collaborator's control of the structure, and the session routes.

### Modified Capabilities

<!-- None. `capability-chat-attachments` (a separate change) is consumed, not
     modified, by this capability. -->

## Impact

**Capability package (new)**

- `libs/capabilities/fred-capability-word-template/` - `docmap.py`,
  `analysis.py`, `operations.py`, `render.py`, `inline.py`,
  `session_document.py`, `content.py`, `images.py`, `store.py`, `router.py`,
  `capability.py`, one migration `w7t4d5e6f7a8`; 294 tests.

**Platform wiring**

- `apps/fred-agents`: dependency and editable source for the package.
- Shared preparation worker and control-plane asset admission for the saved
  library and the platform default; Knowledge Flow's configured text model
  analyses templates through a bounded internal route.
- Combined Alembic checks: the capability's tree registered with its own
  version table.

**Frontend**

- `features/capabilities/word_template/`: library widget with preparation
  status, platform settings panel, side panel (Rédaction and Aperçu tabs),
  generated API client.
  Platform settings list every active template in a scrollable inline list and
  let managers edit names or add and remove individual files before one Save.
- Consumes the `onChatAttachment` hook from `add-capability-chat-attachments`.

**Contracts and docs**

- The shared preparation contract gains a text port and ordered asset hashes.
  The platform result exposes its ordered template labels and hashes to runtime turns.
  `writable_document` is unchanged.
