## Purpose

Lets an agent produce a document by filling and writing into an organisation's
Word template as it is - any template, without preparing it - while the
collaborator keeps control of the document's structure and reviews it part by
part.

## ADDED Requirements

### Requirement: The document is a base plus an ordered edit log

A session's document SHALL be its base (a template of the agent's library, or
a Word file attached in the session) plus the ordered list of edit batches
applied to it, each authored by the model or the collaborator. Every output
(preview, download, the map the model reads) SHALL be that base with every
batch replayed, so it is reproducible and the last batch can be undone.

#### Scenario: Undoing the last edit

- **WHEN** the last batch of a session is undone
- **THEN** the document is the base with every earlier batch replayed
- **AND** nothing of the undone batch remains

The model SHALL undo on its own only a batch applied in the current turn (a
refused batch changed nothing and needs no undo). Undoing a batch from an
earlier turn, already shown to the collaborator, SHALL be refused unless the
model declares that the collaborator asked for it, which goes through the
platform approval gate.

#### Scenario: Undo to repair a refused batch

- **WHEN** no batch was applied in this turn and the model calls undo without declaring a request
- **THEN** nothing is undone and the reply says a refused batch changed nothing

#### Scenario: The base is fixed by the first edit

- **WHEN** a session already has edits on one base and the model asks to switch to another
- **THEN** the switch is refused
- **AND** the refusal says that switching means starting over with the collaborator's agreement

### Requirement: The model reads the document through addressed parts

The engine SHALL expose the document as a map in which every paragraph, table,
row, cell, header, footer and text box has a positional address, split into
readable parts at the top-level headings (or into chunks for a document
without headings), plus one part for the headers and footers. What comes
before the first heading is part "0", so part N is the chapter the template
numbers N; a document without headings counts its parts from "1". An
overlong chapter SHALL be read in pieces "N", "Nb", "Nc"..., one chapter for
every rule that counts parts, so the chapters after it keep their numbers. The
model SHALL
be able to read one or several parts in one call. An unknown part id SHALL be
refused with the list of parts.

#### Scenario: Reading several parts in one call

- **WHEN** the model reads parts "2, 3, hf"
- **THEN** it receives each part's current content with its addresses

#### Scenario: A part named instead of numbered

- **WHEN** the model asks for a part by its title
- **THEN** the call is refused with the list of part ids
- **AND** the refusal is returned to the model as a plain result, not as a failure

### Requirement: The template analysis is read as the model wrote it

Every role and repeatable block of the template analysis SHALL be resolved
against the base's map, whether its address is a single address, a range, a
comma- or semicolon-separated list of both, or a range whose end is written
relative to its start (`T1.R3.C1.P3–P4` ends at `T1.R3.C1.P4`). A range
written end first SHALL cover the same elements. An address absent from the
map SHALL be skipped without discarding the rest of the entry. A text the
analysis marks both as fixed wording and as guidance or placeholder, or a
body paragraph coloured whole, SHALL NOT be protected as fixed wording; a
fixed paragraph with only a coloured passage (such as a link) SHALL stay
protected.

#### Scenario: A list of addresses

- **WHEN** the analysis marks `P3, P5–P6` as guidance
- **THEN** P3, P5 and P6 are tracked as text still to write

#### Scenario: A range inside one cell

- **WHEN** the analysis marks `T1.R3.C1.P3–P4` as placeholders
- **THEN** only the third and fourth paragraphs of that cell are covered
- **AND** no body paragraph after the table is covered

### Requirement: Written text is well formed whatever operation carries it

A model `set_text` whose text holds several paragraphs or list items SHALL
be handled, stored and gated as a `write` of that one place, so the text
becomes paragraphs and lists in the template's look rather than one
paragraph of line breaks. A `set_text` that replaces a body paragraph SHALL
drop the paragraph's own text colour (the mark of a template's guidance);
in a cell, header, footer or text box the colour SHALL be kept.

#### Scenario: A chapter sent as set_text

- **WHEN** the model sets a blue guidance paragraph to three paragraphs and a list
- **THEN** the document holds three paragraphs and a list in the body's colour
- **AND** the stored batch is a `write` of that paragraph

#### Scenario: A heading inside a set_text

- **WHEN** a `set_text` text holds a "#" heading line among several lines
- **THEN** the batch is handled like a `write` adding that heading

### Requirement: What Word computes is never written by the model

A model batch SHALL be refused when it removes or rewrites a line of the
table of contents, or rewrites a paragraph holding a field (page number,
date, file name); the refusal SHALL say that Word computes it. A number the
model types before a heading that Word numbers itself SHALL be dropped
before the batch is stored. The collaborator's edits and the replay of a
stored log SHALL NOT be limited.

#### Scenario: The table of contents retyped

- **WHEN** the model removes the table of contents to write its own
- **THEN** nothing is applied and the reply says Word updates it itself

#### Scenario: A numbered heading

- **WHEN** the model sets a numbered heading to "7 Organisation"
- **THEN** the stored text is "Organisation" and Word shows "7 Organisation" once

### Requirement: Written text looks like the template's own text

Text the model writes in the body SHALL take the explicit colour the
template's own body text carries (such as "auto" over a grey style), and
SHALL NOT keep Word's placeholder character style once a placeholder is
filled. A written text SHALL NOT repeat the heading right above it, and a
`replace_text` of a whole paragraph with Markdown SHALL be written as that
paragraph's text.

#### Scenario: A grey default style

- **WHEN** the template's styles are grey and its text is black by an explicit colour
- **THEN** the text the model writes in place of guidance is black too

### Requirement: A batch is applied whole or not at all

A batch SHALL be validated as a whole before anything is applied: every
address refers to the document as it was before the batch, and an unknown
address, an overlap between operations or an invalid range SHALL reject the
whole batch with every problem listed.

#### Scenario: One invalid operation

- **WHEN** a batch contains one valid and one invalid operation
- **THEN** nothing is applied
- **AND** the reply lists the problem of the invalid operation

### Requirement: The model edits only a document it has read

A model batch SHALL be refused unless every part it addresses was shown to
the model as it is now (by a read, or by an applied edit's reply, which shows
the parts the edit touched) after the last change of addresses: the choice of
a base, a structural edit (`write`, `insert_after`, `repeat`, `remove`) or an
undo. The refusal SHALL name the parts to read. A result of the same model step
as the edit SHALL NOT count. A model batch planned on a read older than a
collaborator's edit SHALL be refused with a request to read again.

#### Scenario: Editing the part an edit's reply just showed

- **WHEN** a structural edit of part 1 was applied and its reply shows part 1
- **THEN** the next batch on part 1 runs without another read

#### Scenario: Editing another part after a structural edit

- **WHEN** the model read parts 1 and 2, then a structural edit of part 1 was applied
- **THEN** a batch on part 2 is refused with a request to read part 2 again

#### Scenario: Editing after the collaborator changed the document

- **WHEN** the collaborator edited the document after the model's last read
- **THEN** the model's next batch is refused until it reads again

### Requirement: One edit per model step

When one model message carries several `edit_document` calls, only the first
SHALL run; each other call SHALL receive its own refusal under its own call
id, so calls and results stay paired.

#### Scenario: Two edits in one step

- **WHEN** a model message carries two `edit_document` calls
- **THEN** the first runs and the second is refused as "one edit at a time"

### Requirement: Written content goes into one part per turn

A model batch that writes content into the body (`write` or `insert_after` on
body paragraphs) SHALL touch only one part, and only the part already written
in the same turn, until the collaborator answers. The reply of an applied
batch that writes content SHALL name that part and tell the model to show it
before writing another. Filling fields and table cells (forms, cover page,
headers, footers) SHALL NOT be limited.

#### Scenario: Writing a second chapter in the same turn

- **WHEN** the model wrote chapter 1 in this turn and sends a batch writing chapter 2
- **THEN** the batch is refused with a request to show what was written and wait

#### Scenario: Filling a form in one turn

- **WHEN** the model fills cells of several table blocks in one turn
- **THEN** every batch runs

### Requirement: The template's structure is kept

A model batch SHALL be refused when it:
- removes every copy of a table block of the base (a table of more than one
  cell; a one-cell frame, such as an image frame, is not a block), or removes
  a copy while writing a Markdown table in the same batch;
- writes over a heading of the template (a `write` range that includes
  one); a heading added later may be rewritten;
- rewrites whole (`write`, `set_text`) a body paragraph the template analysis
  marks as fixed wording, unless the batch declares `changes_template`.

A change of a detail inside a fixed sentence (`replace_text`), headers and
footers, and the collaborator's own edits SHALL NOT be limited. Removing a
whole chapter with its heading SHALL remain possible, through the approval
gate.

#### Scenario: Rebuilding a form in its own layout

- **WHEN** the model removes the only copy of a template table and writes a Markdown table
- **THEN** the batch is refused and the table is kept

#### Scenario: Writing over a heading

- **WHEN** a `write` range includes the template heading "Context"
- **THEN** the batch is refused with a request to write between the headings

#### Scenario: Rewriting a fixed clause

- **WHEN** the model replaces a fixed paragraph without declaring `changes_template`
- **THEN** the batch is refused with the way to ask the collaborator for it

### Requirement: The table of contents follows the headings

After every batch, the engine SHALL rebuild the lines of a document's table
of contents (a Word TOC field) from its headings of the levels the field
lists: one line per heading, in document order, with the heading's number
computed from the template's numbering and its current text, in the style
of the template's own lines of that level, each linked to a bookmark on its
heading (added when missing). A page number SHALL be kept from the line of
the same heading, else taken from the line before. When the headings give
the same lines as before, the table of contents SHALL be left untouched. The downloaded file SHALL
ask Word to update its fields on opening, so page numbers are recomputed.

#### Scenario: Chapters swapped and a sub-heading added

- **WHEN** chapter 2 is moved before chapter 1 and a sub-heading is added
- **THEN** the preview's table of contents lists the chapters in their new order, renumbered, with a line for the new sub-heading

#### Scenario: Opening the download in Word

- **WHEN** the collaborator downloads the document
- **THEN** Word offers to update its fields, and page numbers are computed

### Requirement: A chapter changes place, and so number, by a move

Word numbers headings by their place. A `move` operation SHALL move a range
of top-level body blocks before or after another block; with a heading as
`from` and no `to`, its whole section moves, and `after` a heading means
after its whole section. A move SHALL be alone in its batch, never touch the
table of contents or a section break, and go through the approval gate. A
model batch whose `set_text` only gives a numbered heading a typed number
SHALL be refused with the way to move the chapter instead. Paragraphs
written in place of a caption SHALL NOT take the caption's style.

#### Scenario: Planning wanted as chapter 3

- **WHEN** the collaborator wants chapter 4 "Planning" before chapter 3 and approves the move
- **THEN** "Planning" is chapter 3 with its sub-sections and content, and chapter 3 became 4

#### Scenario: Renumbering by typing

- **WHEN** the model sets a numbered heading to "3. Planning" over "Planning"
- **THEN** nothing is applied and the reply explains how to move the chapter

### Requirement: The collaborator decides the document's structure

The model SHALL follow the template's chapters: a model batch that adds a
heading (a Markdown heading line in `write` or `insert_after`, or a one-line
`set_text`) of a level the template does not use below its chapters SHALL be
refused unless it declares `changes_template`, which the model sets only when
the collaborator asked for a new chapter. A sub-heading of a level the
template already uses below its chapters SHALL run without approval, in the
template's heading style and numbering, so it reaches the table of contents.
A bold line that starts with a typed section number ("**3.2 Costs**") SHALL
be refused: it is a sub-heading without its numbering, or a title whose
number Word cannot keep. A model batch that removes content
or declares `changes_template` SHALL go through the platform approval gate
before it runs. The gate's question SHALL say in
plain language that the agent wants to change the document's structure and
point to the agent's message, which states exactly what will change. Switching
the document's base to an attached file SHALL also be approved.

A batch SHALL be checked when the model proposes it, before the gate: the
guards and a trial of the batch on the current document, nothing stored. A
batch that would be refused SHALL NOT reach the gate: the model SHALL be asked
once to plan its step again with the reasons, and a batch still refused then
SHALL receive its refusal as the tool result.

#### Scenario: An approval for a batch the engine refuses

- **WHEN** the model proposes a removal of the only copy of a template table
- **THEN** no approval is asked, and the model plans again knowing why

#### Scenario: The agent adds a chapter on its own

- **WHEN** the model sends a batch whose Markdown contains a chapter-level heading line, without `changes_template`
- **THEN** the batch is refused before any approval

#### Scenario: A template whose outline is set

- **WHEN** the template's analysis finds real titles in every heading (a contract) and the model writes titled points in a chapter that has the template's sub-headings
- **THEN** its titles are bold lines and the chapter keeps exactly the template's sub-headings
- **AND** in a chapter the template left without sub-headings, the titles become sub-chapters only once the model has named them and the collaborator approved the batch (`changes_template`); a sub-chapter is added the same way to a chapter with sub-headings when the collaborator asks

#### Scenario: The agent splits a chapter into sub-sections

- **WHEN** the template uses level-2 headings and the model writes "## Context" lines in a chapter
- **THEN** the batch runs without approval
- **AND** each sub-heading takes the template's level-2 style and numbering and appears in the refreshed table of contents

#### Scenario: A renamed chapter heading under a write

- **WHEN** a model `write` range includes a chapter heading whose text was renamed
- **THEN** nothing is applied and the reply says to rename with set_text or remove the chapter

#### Scenario: Phases with their goals

- **WHEN** a template with one sub-heading level gets "**2. Phase 1**" then "### 2.1 Goals" lines
- **THEN** "Phase 1" becomes a sub-heading and "Goals" stays a bold line
- **AND** bold lines ending with a colon that all introduce a list stay bold, while siblings written alike become sub-headings together

#### Scenario: A sub-heading wrapped in bold

- **WHEN** the model writes the line "**## Context**"
- **THEN** it is handled as the sub-heading line "## Context", never as bold text showing "##"

#### Scenario: Titling a template sub-heading

- **WHEN** a `write` starts right under a template sub-heading and its first line is a heading of the same level
- **THEN** that template sub-heading takes the title, and no second heading is added

#### Scenario: A numbered bold title

- **WHEN** the model writes the line "**3.2 Costs**"
- **THEN** nothing is applied and the reply asks for a sub-heading without its number (or the title without its number when the template has no sub-heading level)

#### Scenario: The collaborator asks for a chapter

- **WHEN** the collaborator asked for a new chapter and the batch declares `changes_template`
- **THEN** the collaborator is asked to approve before anything is applied
- **AND** refusing leaves the document unchanged

#### Scenario: Plain content needs no approval

- **WHEN** the model writes paragraphs and lists under the template's headings
- **THEN** the batch runs without an approval step

### Requirement: Refusals reach the model, failures reach the collaborator

A refusal the model must act on (unknown address, guard, base already fixed)
SHALL be returned as a plain tool result, so the model reads the reason and
answers the collaborator itself. Only real failures (no session, document
unavailable) SHALL be returned as errors.

#### Scenario: A refused batch

- **WHEN** a batch is refused by a guard
- **THEN** the model receives the reason as a plain result
- **AND** the collaborator sees the model's own answer, not a generic failure sentence

When the turn's last `edit_document` was not applied (refused, failed, or
stopped by the platform), the model's final answer SHALL be asked once more
with a note that the document does not hold that content, so the answer does
not claim it does. When a chapter written in the turn still holds the
template's own text (guidance, samples) per the document check, the final
answer SHALL be asked once more with a note that it is not complete. Every
model call SHALL carry today's date.

#### Scenario: A chapter reported as saved after a refused edit

- **WHEN** the turn's last edit was refused and the model's answer follows
- **THEN** the answer is asked again, saying what was not saved

### Requirement: Where the document stands comes from the document

After every applied model batch, the engine SHALL check each part the batch
touched, in the document after the batch, and add the result to the batch's
reply: every place that still holds the base's guidance, sample or
placeholder text, with a plain-language location (the analysis' note for
that text, else the nearest heading or the cell's row label), its current
address and the start of its text, at most ten places per part followed by
the number of the others; and the
[À COMPLÉTER] markers left, which are not errors. A fixed paragraph holding a
placeholder pattern SHALL be reported as a detail to fill inside fixed
wording, never as text to rewrite. Every model call SHALL carry the same
check for the whole document as a count per part, each part named by its
title, and SHALL say so when nothing is left; a body part with nothing under
its heading counts as left.

A base text SHALL count as placeholder text when the analysis marks it as
guidance or placeholder, when it is a body paragraph coloured whole, or when
it holds a placeholder pattern (a bracketed or angle-bracketed field, "XXX",
lorem ipsum, zero-filled dates or numbers). Where an analysis role covers a
whole table or whole rows, only its coloured text or placeholder patterns
SHALL count (its headings and labels are not places to fill); a role naming
a cell or a paragraph counts whole. Table-of-contents lines SHALL NOT count. Placeholder patterns SHALL NOT remove fixed-wording
protection. The check compares texts, not addresses, so it follows the
document through removals, insertions and repeats; it SHALL make no model
call and SHALL NOT block the batch. The engine's principles SHALL tell the
model that a part is finished only when its check reports nothing left, and
otherwise to finish it or tell the collaborator what is left.

#### Scenario: A chapter left half done

- **WHEN** the model writes the first sub-section of a chapter and leaves the guidance of the last one
- **THEN** the reply names that sub-section's guidance as still in place
- **AND** the chapter is counted as not finished in the next model call

#### Scenario: A letter with one part

- **WHEN** the model fills the recipient but leaves the date and the signature
- **THEN** the reply lists the date and the signature fields with their labels

#### Scenario: A marker left on purpose

- **WHEN** a written part holds an [À COMPLÉTER] marker
- **THEN** the reply lists it as to complete, not as a leftover of the template

#### Scenario: A field inside fixed wording

- **WHEN** a fixed paragraph of the base holds a bracketed field
- **THEN** the reply reports the field as a detail to fill inside fixed wording

#### Scenario: A repeated block

- **WHEN** the model repeats a project block and fills only the first copy
- **THEN** the second copy's fields are listed as left

#### Scenario: A part removed with the collaborator's approval

- **WHEN** a part is removed
- **THEN** its template texts are no longer counted
- **AND** the remaining parts are named by their titles, with their new addresses

#### Scenario: An edit that never ran

- **WHEN** a batch was refused or never ran and the model is called again
- **THEN** the places it would have filled are still counted as left

### Requirement: An attached Word file is a source by default

An attached Word file SHALL be a source of information by default. It SHALL
become the document's base only when it is the document to deliver (an
earlier version to update, the form to fill) and the collaborator asks for it
or agrees, through the approval gate. When a library template of the
requested kind exists, the document SHALL start from that template.

#### Scenario: Writing a specification from a needs document

- **WHEN** the collaborator attaches a needs document and asks for a specification from it
- **THEN** the needs document stays a source
- **AND** the document starts from the library's specification template

### Requirement: Text goes only where the template has a place for it

A model batch SHALL be refused when it writes text into a header or footer
Word never shows (a first-page one without the section's "different first
page", an even-page one without odd/even pages; the map marks it, the
document check skips it, the refusal names the one shown), into a paragraph
holding only an image, or moves a paragraph's text into another paragraph
the batch also rewrites. The styled title right above the table of contents
SHALL be kept like the table of contents. The model SHALL change text only,
never claim a change of colour, size, font or alignment, and answer a
request to look at the document by reading it, without editing.

#### Scenario: A name written into an inactive first-page footer

- **WHEN** the model writes into the first-page footer of a section without a different first page
- **THEN** nothing is applied and the reply names the footer Word shows there

#### Scenario: Values shifted down the cover page

- **WHEN** a batch writes the date paragraph's text into the contents title and a name into the date paragraph
- **THEN** nothing is applied and the reply says each paragraph keeps its own value

### Requirement: Unused template parts are removed at the end, with approval

When every part the collaborator wants is written, the model SHALL tell them
which parts of the template went unused and offer to remove them, through a
`remove_unused_template_parts` tool that always goes through the platform
approval gate. The engine, not the model, SHALL find those parts in the
body after the cover page: a section whose heading still holds the
template's sample text and whose content is all untouched template content
(heading and content removed together), and, elsewhere, a paragraph still
holding the template's guidance or sample text or a table holding nothing
else (an empty image frame included). Fixed wording, the cover page, the
table of contents, headers and footers, [À COMPLÉTER] markers and anything
written SHALL be kept. The removal SHALL be one stored batch, so it can be
undone.

#### Scenario: Finishing a document

- **WHEN** chapters 1 to 4 are written and chapter 5 still holds the template's sample heading and text
- **THEN** after the collaborator's approval, chapter 5 is gone with its table-of-contents line, and so are the sample paragraphs and empty frames left in chapters 1 to 4
- **AND** a fixed clause and an [À COMPLÉTER] marker are still there

### Requirement: The model knows the session's template

Whenever a library template is the session's base, every model call SHALL name
it and say it is already loaded, so the model never looks for a template with
other tools (document search finds sources, not templates). Switching with
`select_template` SHALL be mentioned only when the library holds several
templates.

#### Scenario: A library with a single template

- **WHEN** the agent's library holds one template and the model is called
- **THEN** the prompt names that template as already loaded
- **AND** it does not offer to switch templates

### Requirement: Session routes are restricted to the session's owner

Every route under `/capabilities/word_template/sessions/{session_id}` SHALL
check that the caller owns the session and refuse anyone else.

#### Scenario: Another user's session

- **WHEN** an authenticated user calls a route of a session they do not own
- **THEN** the request is refused

### Requirement: The collaborator edits the document directly

The collaborator SHALL be able to read the document as parts and blocks and
edit it (chapter text, cells, cover page and header fields, Duplicate, Remove,
Undo). Each edit SHALL be an ordinary batch authored by the collaborator,
refused with a conflict when the document changed since it was read. The model
SHALL see the collaborator's edits made since its last batch and SHALL NOT be
allowed to edit on a read older than them.

#### Scenario: A stale collaborator edit

- **WHEN** the collaborator saves an edit made on a version the model has since changed
- **THEN** the edit is refused as a conflict and the view reloads

### Requirement: Files removed from the chat are forgotten

The capability SHALL forget an attached Word file or image when the
collaborator removes it from the chat, except a file that is the document's
base and images the document already places.

#### Scenario: A file attached then removed before sending

- **WHEN** the collaborator attaches a Word file and removes it before sending
- **THEN** the capability no longer lists it to the model

#### Scenario: The base is removed from the chat

- **WHEN** the collaborator removes the file that is the document's base
- **THEN** the file is kept and the document is unchanged
