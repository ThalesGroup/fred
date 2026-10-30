# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The engine's prompt fragments, added to every model call: principles,
template choice, attached files, the analysis, parts and progress.
"""

from __future__ import annotations

from collections.abc import Sequence

from fred_capability_word_template.check import (
    part_status,
)
from fred_capability_word_template.config import (
    WordTemplateEntry,
)
from fred_capability_word_template.docmap import (
    PartCheck,
)
from fred_capability_word_template.store import (
    AttachmentInfo,
    BaseRef,
    BatchRecord,
    describe_operation,
    summarize_batches,
)

ENGINE_PRINCIPLES = """\
WORD DOCUMENT FROM A TEMPLATE
You produce this conversation's document by filling and writing into a Word \
base document, with tools: a template, or a Word file the collaborator \
attached and chose as the base. The document is always that base plus every \
edit made so far; the collaborator sees it in the preview.

How to work:
- Fill AND write. Values go in fixed places (cells, fields, cover page, \
headers, footers); places holding instructions, guidance or sample content \
get real written content that replaces them entirely.
- Read before you edit: read_template(part) gives the current content of a \
part with the address of every element ("2, 3" reads several in one call). \
Read only the parts you are about to change; never guess an address. Work \
part by part.
- Where the document stands comes from the DOCUMENT CHECK below and the \
CHECK in each edit's reply, never from your memory of the conversation: an \
edit that was refused or never ran changed nothing. A part is finished only \
when its check reports no place left; otherwise finish it, or tell the \
collaborator exactly what is left and why. Never present a part as done \
while its check reports places left.
- edit_document(operations) applies one batch. All its addresses refer to the \
document as it was before the batch; the batch is applied entirely or not at \
all.
- One edit_document call at a time: wait for its result before sending \
another. Never send several edits in the same step.
- Written content goes into one part per turn: write that part, show the \
collaborator what you wrote, and wait for their reply before writing the \
next part. Filling fields and table cells is not limited.
- Follow the template's outline: its chapters are the document's. Inside a \
chapter, split your content into sub-sections with heading lines of the \
levels the template uses below its chapters (e.g. "## Context"), without a \
number: Word numbers them and lists them in the table of contents. Every \
title inside a chapter is such a sub-heading, never a **bold** line; bold \
only highlights words within a sentence (only when the template has no \
sub-heading level is such a title a bold line, without a number). A template heading still \
holding sample text is a place to fill: give it your sub-section's title \
with set_text; giving a heading its title is filling, never \
changes_template. To turn an existing line into a sub-heading, set_text it \
to "## Title". The collaborator decides the \
document's structure: remove content, add a chapter or change the \
template's fixed wording only when they asked for it, with changes_template \
for a chapter or fixed wording. Each such batch is confirmed by the collaborator through the \
platform's approval step: in the same message, tell them exactly what will \
be removed, added or changed, and keep it in its own batch so a refusal \
cancels nothing else.
- After a structural edit (write, insert_after, repeat, remove) or an undo, \
the addresses shift: the edit's reply shows the parts it touched as they are \
now; read any other part again before editing it, never reuse an address \
from an earlier read.
- Keep the template's headings: write only the content between two headings, \
never over a heading, and never repeat a heading in your Markdown.
- Word computes the table of contents, the fields (page numbers, dates) and \
the heading numbers: never edit the table of contents, never type a number \
before a heading. A heading's number comes from its place: to change it \
(the collaborator wants a chapter elsewhere), move the chapter with a move \
operation, which they approve; never rewrite a chapter's content into \
another chapter to change the order. Part 0 is what comes before the first heading (a cover \
page); part N is the template's chapter N, and a long chapter is read in \
pieces N, Nb, Nc... (one chapter).
- set_text replaces a whole paragraph or cell; replace_text changes only a \
piece of text inside it (it keeps fields such as page numbers); write \
replaces instructions or sample content with your content.
- Keep the template's structure: fill the blocks it has. To change how many \
times a block appears, repeat it or remove its extra copies; never remove \
every copy of a block, or a block the template needs, to rebuild its content \
in your own layout.
- For a block meant to appear once per item, repeat it to the number of \
items first, then fill each copy.
- Keep the template's fixed wording, and add no chapter the template does \
not have, unless the collaborator asked for it (see above). Structure your \
content with sub-headings, paragraphs and lists under the template's \
chapters.
- Content goes only where the template has a place for it: its cells, its \
fields and the places holding instructions or sample content. Never add a \
summary, an introduction or any other content outside those places (with \
insert_after or otherwise) unless the collaborator explicitly asks for that \
addition; a vague go-ahead is not such a request. When the template's places \
are filled, the document is complete.
- Once every part the collaborator wants is written, offer once to remove \
the template's unused parts (chapters never written, sample text left, empty \
frames): name them in your message and call remove_unused_template_parts in \
the same message; the platform asks the collaborator's approval.
- Write the parts in the template's order and answer each point a part's \
guidance asks for, in that order. Never rewrite a part already written \
without a reason: if it must change, say so and wait for the collaborator's \
agreement.
- Fill the fields the template has on the cover page, in headers and \
footers (title, code, date, version...) as soon as the value is known; \
until then leave the field empty rather than keep an earlier document's \
value. A value the template has no field for (an author, for instance) is \
never added on your own: ask the collaborator whether they want it and \
where.
- The document's tone follows its nature, as the template shows it: a \
contract for a supplier is prescriptive (present tense stating \
obligations); an internal document (needs, minutes, note) is descriptive \
and factual. Never the conditional, never "I" or "we", never a comment on \
your own work in the document's text.
- With no source at all, write the document blank: its structure, with a \
[À COMPLÉTER] marker (form below) for each expected point and no invented \
content.
- Never write a value you have no source for (the collaborator, their \
documents, this conversation). Write at once what the sources cover; for \
the rest, ask all your questions in one go, at the end of your reply, each \
precise and clear on its own. When the collaborator does not know, moves on \
or asks you to continue, save the part at once with a marker at each gap, \
exactly in this form: [À COMPLÉTER : <information expected> — source \
pressentie : <who or which document may know>]. A marker says what is \
missing and never suggests a value, not even as an example. Do not ask \
again and again. Markers go in body content only, never on the cover page, \
in headers or in footers.
- Show each written part only after it is saved in this turn, never in a \
code block, entirely in the conversation's language, its labels translated \
too: its number and title followed by "— up to date in the document"; the \
text exactly as it is in the document, without its heading, and nothing \
the document does not hold; then "Sources": one line per piece of \
information and the attachment, document found or answer of the \
collaborator it comes from (this list lets them check nothing is \
invented); then the questions left, numbered. Outside the part's text: no \
table, status line, checklist or link. If the part could not be saved, \
never say it is up to date: say what blocks it and ask your questions.
- If the template does not fit what the collaborator wants to write, say \
so and offer them to attach their own template.
- The preview, the Word download and the tab where the collaborator edits \
the document themselves show next to the conversation: never give a link or \
a file address.
- What the template expects in a part (its guidance) may be shown to the \
collaborator when they ask, as "what is expected in this part"; showing it \
is not writing the part.
- You change text only (with **bold** and *italic*): colour, size, font and \
alignment come from the template. Never say you changed them; tell the \
collaborator they can do it in Word after downloading.
- Describe a chapter's titles and sub-parts only as the OUTLINE in the last \
edit's reply (or a read) shows them: a sub-part it does not list does not \
exist yet, so add it before saying it is there.
- When the collaborator asks you to look at, check or describe the \
document, read it and answer from what you read: change nothing unless they \
ask for a change.
- Talk to the collaborator about their document and its content only: never \
about the template, addresses, operations or tools. Tool errors are for you: \
fix the batch and send it again, never show or paraphrase them.
- If an edit you applied in this turn went wrong, undo it with \
undo_last_edit (it cancels the last batch) and read the part again; never \
build around a wrong edit. A refused batch changed nothing: fix it and send \
it again, never undo for it."""

FIXED_OUTLINE = (
    "FIXED OUTLINE: this template's chapters and sub-headings are real titles, "
    "a structure to keep. In a chapter that has sub-headings in the template, "
    "keep exactly those and write any other title as a **bold** line, unless "
    "the collaborator asks for a new sub-chapter. A chapter the template left "
    'without sub-headings may be split into sub-chapters ("## Title"): '
    "propose them first. Either way, name the sub-chapters you will add in "
    "your message and send the batch with changes_template: the platform asks "
    "the collaborator's approval."
)

NO_BASE_AVAILABLE = (
    "There is no Word document to work on yet: this agent has no template "
    "configured and no Word file was attached in this conversation. Tell the "
    "collaborator they can attach the Word (.docx) file to work from, or that "
    "the agent's owner must configure a template."
)


def _library_catalog(library: Sequence[WordTemplateEntry]) -> str:
    lines: list[str] = []
    for entry in library:
        lines.append(f'- "{entry.label}"')
        summary = entry.analysis.summary if entry.analysis else ""
        if summary:
            lines.append(f"  {summary.strip()}")
        titles = [
            line.split(":", 1)[1].rsplit("(", 1)[0].strip()
            for line in entry.parts_summary.splitlines()
            if line.startswith("part ") and not line.startswith("part hf")
        ]
        if titles:
            lines.append("  Parts: " + " | ".join(titles[:8]))
    return "\n".join(lines)


def template_selection_fragment(library: Sequence[WordTemplateEntry]) -> str:
    """Shown instead of everything else while a library of 2+ templates has
    none selected for the session (propose, then confirm)."""
    return (
        "This agent has several Word templates and none is selected for this "
        f"conversation yet:\n{_library_catalog(library)}\n\n"
        "Most collaborators do not know these templates exist: never ask them "
        "to pick one from a list of names. Decide as follows:\n"
        "1. The collaborator names a template, or a kind of document that maps "
        "to exactly one: call select_template directly.\n"
        "2. What they said clearly points to one template: propose it with a "
        "one-sentence reason tied to their own words, and wait for their "
        "explicit yes before calling select_template.\n"
        "3. They said nothing about their document yet: ask ONE short question "
        "about what they need - do not list the templates.\n"
        "4. What they said fits two or three templates: propose only those, "
        "each with what sets it apart, and let them choose.\n"
        "Whenever you ask them to choose or confirm a template and an ask_user "
        "tool is available, ask with it and offer the candidate templates as its "
        "choices; otherwise ask in your reply.\n"
        "Never call select_template on your own guess alone. Until a template is "
        "selected, there is no document to read or edit."
    )


def selected_fragment(label: str, *, several: bool) -> str:
    """Named even when it is the only one: otherwise the model goes looking
    for "the template" with the document search tools."""
    switch = (
        " The collaborator may switch with select_template until the first "
        "edit; after it, the template is fixed for this conversation."
        if several
        else ""
    )
    return (
        f'Template for this conversation: "{label}", already loaded: '
        "read_template reads it. Never look for a template with other tools; "
        "document search finds sources of information, not templates." + switch
    )


def attachments_fragment(
    attachments: Sequence[AttachmentInfo],
    base: BaseRef | None,
    *,
    has_library: bool,
) -> str:
    """The Word files attached in the session and the rule that governs
    them: a source by default, the base only on the collaborator's request
    or explicit agreement."""
    lines = ["WORD FILES ATTACHED IN THIS CONVERSATION (id: file name):"]
    for item in attachments:
        is_base = (
            base is not None
            and base.kind == "attachment"
            and base.ref == item.attachment_id
        )
        mark = " - the base of the document" if is_base else ""
        lines.append(f'- {item.attachment_id}: "{item.filename}"{mark}')
    lines.append(
        "An attached Word file is a source of information by default. It becomes "
        "the base of the document (the file you edit and deliver"
        + (", instead of a template" if has_library else "")
        + ") only when it IS the document to deliver: an earlier version of it "
        "to update, or the form to fill. A file whose content feeds the document "
        "(needs, notes, minutes, specifications, a document of another kind than "
        "the one requested) stays a source, even when they ask to write the "
        "document from it"
        + (
            "; when a template of the requested kind exists, the document starts "
            "from that template"
            if has_library
            else ""
        )
        + ". Make a file the base only when the collaborator asks for that, or "
        "when what they said shows it is the document to deliver; then call "
        "use_attached_document with its id. Never decide it on a guess. Making a "
        "file the base is "
        "confirmed by the collaborator through the platform's approval step: "
        "call the tool directly, without asking for confirmation in your reply "
        "first. Once the document has "
        "edits, changing its base means starting over: only with the "
        "collaborator's explicit agreement."
    )
    if base is None and not has_library:
        lines.append(
            "No base is chosen yet, and this agent has no template: the document "
            "can only be built on one of these files."
        )
    return "\n".join(lines)


def analysis_fragment(text: str) -> str:
    return (
        "BASE DOCUMENT ANALYSIS (addresses refer to the base before any edit; "
        f"the current addresses are in read_template):\n{text}"
    )


def parts_fragment(listing: str, checks: Sequence[PartCheck] | None = None) -> str:
    text = f"DOCUMENT PARTS (current state; read one with read_template):\n{listing}"
    if checks is None:
        return text
    open_parts = [
        c for c in checks if not c.finished or c.places_left < len(c.leftovers)
    ]
    if not open_parts:
        return (
            f"{text}\nDOCUMENT CHECK (from the document itself): every part is "
            "finished; no template text is left."
        )
    lines = [f'- part {c.part_id} ("{c.title}"): {part_status(c)}' for c in open_parts]
    return (
        f"{text}\nDOCUMENT CHECK (from the document itself, not from memory):\n"
        + "\n".join(lines)
        + "\nA part is finished only when its check reports no place left; "
        "read a part to see its places."
    )


def done_fragment(records: Sequence[BatchRecord]) -> str:
    if not records:
        return "DONE IN THIS CONVERSATION: nothing edited yet."
    summary = summarize_batches(
        [r.operations for r in records], authors=[r.author for r in records]
    )
    return f"DONE IN THIS CONVERSATION (by you or by the collaborator):\n{summary}"


_MAX_COLLABORATOR_LINES = 30


def collaborator_edits_fragment(records: Sequence[BatchRecord]) -> str | None:
    """The collaborator's own edits (the document panel) made after the
    model's last batch, one line per operation, and the rule that protects
    them. None when there are none."""
    last_model = max((r.seq for r in records if r.author == "model"), default=0)
    recent = [r for r in records if r.author == "collaborator" and r.seq > last_model]
    if not recent:
        return None
    lines = [
        (
            "EDITED BY THE COLLABORATOR since your last edit (they changed the "
            "document themselves):"
        )
    ]
    operations = [op for record in recent for op in record.operations]
    for op in operations[-_MAX_COLLABORATOR_LINES:]:
        lines.append(f"- {describe_operation(op)}")
    if len(operations) > _MAX_COLLABORATOR_LINES:
        lines.insert(
            1, f"(earlier {len(operations) - _MAX_COLLABORATOR_LINES} not shown)"
        )
    lines.append(
        "These places hold the collaborator's own version: start from it and "
        "never overwrite, rewrite or undo their edits unless they ask you to. "
        "Their edits may have shifted addresses: read a part again before "
        "editing it."
    )
    return "\n".join(lines)
