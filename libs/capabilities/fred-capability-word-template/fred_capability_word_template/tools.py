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

"""The model's tools: read the document, edit it in batches, undo, remove the
template's unused parts, choose its base (a library template or an attached
Word file).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from typing import Any

from fred_sdk.contracts.context import ToolInvocationResult
from langchain_core.tools import BaseTool, tool

from fred_capability_word_template.check import (
    CheckBasis,
    batch_check_basis,
    touched_checks,
    unused_parts,
)
from fred_capability_word_template.config import (
    normalized,
)
from fred_capability_word_template.docmap import (
    DocMap,
    build_map,
    outline,
    render_part,
    render_parts,
)
from fred_capability_word_template.documents import (
    CLEANUP_TOOL,
    NO_BASE_YET,
    NO_TEMPLATE_YET,
    READ_MARK,
    SEEN,
    SHIFTED,
    UNAVAILABLE,
    Active,
    DocState,
    Documents,
    chapters_of,
    current_document,
    log_mark,
    operation_addresses,
    part_ids_of,
    reraise_run_stop,
    state_from,
    try_batch,
    written_body_addresses,
)
from fred_capability_word_template.operations import BatchError, apply_batch
from fred_capability_word_template.session_document import (
    BaseUnavailable,
    save_snapshot,
)
from fred_capability_word_template.store import (
    WORD_TEMPLATE_CAPABILITY_ID,
    BaseRef,
    Batch,
    BatchConflict,
    describe_batch,
    get_word_template_store,
)

logger = logging.getLogger(__name__)

_TOOL_REF = WORD_TEMPLATE_CAPABILITY_ID
# The edit tool returns the updated map of the parts it touched, up to this
# size; beyond, the model reads the parts it needs.
_MAX_EDIT_REPLY_CHARS = 12_000


_STRUCTURAL = {"write", "insert_after", "repeat", "remove"}


def _edit_reply(
    before: DocMap,
    after_docx: bytes,
    batch: Batch,
    seq: int,
    basis: CheckBasis | None = None,
) -> str:
    """Confirmation + the updated map of the parts the batch touched (part
    ids taken from the state before, rendered from the state after), then
    the check of those parts."""
    after = build_map(after_docx)
    ids = part_ids_of(before, operation_addresses(batch))
    structural = any(op.get("op") in _STRUCTURAL for op in batch)
    lines = [f"Applied {len(batch)} operation(s) as edit #{seq}."]
    if structural:
        lines.append(
            f"{SHIFTED}: the parts shown below are current; read any other "
            "part again (read_template) before editing it, never reuse an "
            "address from an earlier read."
        )
    written = chapters_of(part_ids_of(before, written_body_addresses(batch)))
    if written:
        lines.append(
            f"Written content of this turn: part {', '.join(written)}. You may "
            "add to it, but write another part only after the collaborator's "
            "reply: show them what you wrote first."
        )
    for chapter in dict.fromkeys(chapters_of(ids)):
        if (line := outline(after, chapter)) is not None:
            lines.append(line)
    rendered: list[str] = []
    size = 0
    for part_id in ids:
        try:
            text = render_part(
                after, part_id, full=basis.full if basis else frozenset()
            )
        except KeyError:
            continue
        if size + len(text) > _MAX_EDIT_REPLY_CHARS:
            rendered.append(
                f"(part {part_id} not shown: read it with read_template before editing it)"
            )
            continue
        size += len(text)
        rendered.append(f"Part {part_id} now:\n{text}")
    lines.extend(rendered)
    if structural:
        lines.append("Parts now:\n" + render_parts(after))
    if basis is not None:
        lines.extend(touched_checks(before, after, ids, basis))
    return "\n\n".join(lines)


def _edit_reply_safe(
    before_docx: bytes,
    after_docx: bytes,
    batch: Batch,
    seq: int,
    basis: CheckBasis | None = None,
) -> str:
    """The reply of an applied batch: never a failure, the batch is stored."""
    try:
        return _edit_reply(build_map(before_docx), after_docx, batch, seq, basis)
    except Exception:  # noqa: BLE001 - the edit is applied; only its summary is lost
        logger.warning(
            "[WORD_TEMPLATE][TOOL] edit #%d: reply could not be built",
            seq,
            exc_info=True,
        )
        return f"Applied {len(batch)} operation(s) as edit #{seq}. Read the part again."


def _tool_error(message: str) -> tuple[str, ToolInvocationResult]:
    """A real failure (no session, document unavailable): the runtime shows
    its generic failure sentence instead of the model's answer."""
    return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)


def _refused(message: str) -> tuple[str, ToolInvocationResult]:
    """A refusal the model must read and act on (wrong address, base
    already fixed, ...). Not an error for the runtime, which would replace the
    model's own answer to the collaborator with it."""
    return message, ToolInvocationResult(tool_ref=_TOOL_REF)


def _ok(message: str) -> tuple[str, ToolInvocationResult]:
    return message, ToolInvocationResult(tool_ref=_TOOL_REF)


def _norm_id(value: str) -> str:
    return value.strip().strip('"').lower()


def build_tools(docs: Documents) -> list[BaseTool]:
    store = get_word_template_store

    def _not_ready(message: str) -> tuple[str, ToolInvocationResult]:
        # No template chosen yet is the model's to handle; a missing session or
        # an unloadable document is a real failure.
        if message in (NO_TEMPLATE_YET, NO_BASE_YET):
            return _refused(message)
        return _tool_error(message)

    def _seen(batches: Sequence[Batch]) -> None:
        if docs.session_id:
            SEEN.put(docs.session_id, log_mark(batches))

    @tool("read_template", response_format="content_and_artifact")
    async def read_template(part: str) -> tuple[str, ToolInvocationResult]:
        """Read parts of this session's document as they are NOW (the Word
        template plus every edit so far), with the address of every
        paragraph, table, row and cell. Read a part before editing it, and
        again after a structural edit elsewhere (an edit's reply shows the
        parts it touched as they are now).

        part: a part id from the DOCUMENT PARTS list in the system prompt
        ("1", "2", ...; "hf" for headers and footers), or several separated
        by commas ("2, 3, hf") to read them in one call."""
        current = await current_document(docs)
        if isinstance(current, str):
            return _not_ready(current)
        active, records, state = current
        ids = [p for p in re.split(r"[\s,;]+", part.strip()) if p]
        doc_map = await asyncio.to_thread(build_map, state.docx)
        basis = await batch_check_basis(docs, active)
        full = basis.full if basis is not None else frozenset()
        texts: list[str] = []
        unknown: list[str] = []
        for part_id in ids:
            try:
                texts.append(
                    f"Part {part_id} {READ_MARK}\n"
                    f"{render_part(doc_map, part_id, full=full)}"
                )
            except KeyError:
                unknown.append(part_id)
        if unknown or not ids:
            return _refused(
                f'"{", ".join(unknown) or part}" is not a part id of this document: '
                'use the id before the colon ("1", "2", ..., "hf"). '
                f"Parts:\n{state.parts_listing}"
            )
        _seen([r.operations for r in records])
        return _ok("\n\n".join(texts))

    @tool("edit_document", response_format="content_and_artifact")
    async def edit_document(
        operations: list[dict[str, Any]],
        changes_template: bool = False,
    ) -> tuple[str, ToolInvocationResult]:
        """Apply ONE batch of edits to this session's document.

        One call at a time: wait for this call's result before sending
        another edit_document; never send several in the same step.

        Every address in the batch refers to the document as it is BEFORE
        this batch (as last read). The batch is checked as a whole: if any
        operation is wrong, nothing is applied and every problem is listed.

        Keep the template's structure: change how many times a block
        appears with repeat or by removing extra copies, never by removing
        every copy of a block to rebuild its content in another layout.

        operations: a list of objects, each with an "op":
        - {"op": "set_text", "address": A, "text": T} - replace the whole
          text of a paragraph or a cell, keeping its formatting (inline
          **bold** and *italic* allowed). Several paragraphs or list items
          in T are written as with write, at that place.
        - {"op": "replace_text", "address": A, "find": F, "replace": R} -
          replace F by R inside a paragraph, a cell, a header or footer
          (e.g. "F1") or a text box, keeping everything else (fields such
          as page numbers stay). Copy F exactly from the map.
        - {"op": "write", "from": A, "to": B, "markdown": M} - replace the
          paragraphs and tables from A to B (same place, reading order), or
          the whole content of one cell (from = the cell, no "to"), with
          Markdown: paragraphs, "- " bullets, "1. " numbered items,
          **bold**, | tables | in the body only, and an image from the
          IMAGES AVAILABLE list alone on its line as
          ![caption](img:<id>). A heading line of a level the template uses
          below its chapters ("## Title", no number) adds a sub-heading; a
          chapter-level heading line only when the collaborator asked for a
          new chapter, with changes_template.
        - {"op": "insert_after", "address": A, "markdown": M} - add Markdown
          content right after a paragraph or a table. Only when the
          collaborator explicitly asked for content the template has no
          place for.
        - {"op": "repeat", "from": A, "to": B, "count": N} - add N copies of
          the paragraphs/tables, or of the table rows, from A to B, right
          after B.
        - {"op": "remove", "from": A, "to": B} - delete the paragraphs/tables
          or table rows from A to B.
        - {"op": "move", "from": H, "before": X} (or "after": X) - move a
          chapter or sub-section (H its heading, the whole section moves)
          before X, or after X's whole section; "to" moves a range of blocks
          instead. Word numbers headings by their place: this is how a
          chapter changes number. In a batch of its own.

        changes_template: true only when the collaborator asked to change
        the template: its fixed wording (rewrite or remove a fixed
        paragraph) or its outline (add a chapter).

        The collaborator confirms through the platform's approval step every
        batch that removes or moves content or declares changes_template.
        In the same message as such a batch, tell them exactly what will be
        removed, added or changed, so they can check it before accepting;
        keep such changes in their own batch so a refusal cancels nothing
        else."""
        current = await current_document(docs)
        if isinstance(current, str):
            return _not_ready(current)
        active, records, state = current
        batches = [r.operations for r in records]
        assert docs.session_id is not None
        basis = await batch_check_basis(docs, active)
        try:
            trial = await try_batch(
                docs,
                active,
                records,
                state,
                operations,
                changes_template=changes_template,
                fixed_outline=basis is not None and basis.fixed_outline,
            )
        except BaseUnavailable as exc:
            reraise_run_stop(exc)
            return _tool_error(UNAVAILABLE)
        if isinstance(trial, str):
            return _refused(trial)
        return await _store(active, batches, state, trial.batch, trial.docx)

    async def _store(
        active: Active,
        batches: list[Batch],
        state: DocState,
        batch: Batch,
        new_docx: bytes,
    ) -> tuple[str, ToolInvocationResult]:
        """Store an applied model batch and reply with the parts it touched."""
        assert docs.session_id is not None
        try:
            seq = await store().append_batch(
                docs.session_id,
                active.base,
                batch,
                docs.writer,
                expected_count=len(batches),
            )
        except BatchConflict:
            return _refused(
                "Another edit was applied at the same time, so this batch was not "
                "applied: read the part again and send the batch once more."
            )
        new_log = [*batches, batch]
        _seen(new_log)
        reply = await asyncio.to_thread(
            _edit_reply_safe,
            state.docx,
            new_docx,
            batch,
            seq,
            await batch_check_basis(docs, active),
        )
        await docs.remember(
            active.base, new_log, await asyncio.to_thread(state_from, new_docx)
        )
        logger.info(
            "[WORD_TEMPLATE][TOOL] session=%s edit #%d: %s",
            docs.session_id,
            seq,
            describe_batch(batch),
        )
        return _ok(reply)

    @tool(CLEANUP_TOOL, response_format="content_and_artifact")
    async def remove_unused_template_parts() -> tuple[str, ToolInvocationResult]:
        """Remove the template's parts left unused, in one edit: chapters and
        sub-sections never written (sample heading and sample content), and
        the guidance, sample text and empty frames left elsewhere. Fixed
        wording, the cover page, headers and footers, [À COMPLÉTER] markers
        and everything written stay.

        Offer it once every part the collaborator wants is written: in the
        same message, tell them which parts will go (the chapters never
        written, the places the DOCUMENT CHECK still lists); the platform
        asks their approval. It can be undone like any edit."""
        current = await current_document(docs)
        if isinstance(current, str):
            return _not_ready(current)
        active, records, state = current
        basis = await batch_check_basis(docs, active)
        if basis is None:
            return _tool_error(UNAVAILABLE)
        found = await asyncio.to_thread(unused_parts, state.docx, basis)
        if not found:
            return _ok("Nothing to remove: no unused part of the template is left.")
        batch: Batch = [{"op": "remove", "from": r.start, "to": r.end} for r in found]
        try:
            new_docx = await asyncio.to_thread(apply_batch, state.docx, batch)
        except BatchError as exc:
            logger.warning(
                "[WORD_TEMPLATE][TOOL] session=%s cleanup refused: %s",
                docs.session_id,
                exc.problems,
            )
            return _tool_error(UNAVAILABLE)
        stored, result = await _store(
            active, [r.operations for r in records], state, batch, new_docx
        )
        if not stored.startswith("Applied"):
            return stored, result
        removed = "\n".join(f"- {r.label}" for r in found if r.label)
        return f"{stored}\n\nRemoved, as unused template parts:\n{removed}", result

    @tool("undo_last_edit", response_format="content_and_artifact")
    async def undo_last_edit(
        collaborator_asked: bool = False,
    ) -> tuple[str, ToolInvocationResult]:
        """Cancel the last edit_document batch of this session (the whole
        batch), then read the part again. On your own, undo only an edit you
        applied in this turn that went wrong; a refused batch changed nothing
        and needs no undo.

        collaborator_asked: true only when the collaborator asked to undo an
        edit made earlier; they confirm it through the platform's approval
        step."""
        if not docs.session_id:
            return _tool_error("No active session.")
        try:
            records = await store().list_batch_records(docs.session_id)
            if records and records[-1].author == "collaborator":
                return _refused(
                    "Nothing undone: the last edit is the collaborator's own. Ask "
                    "them before changing it."
                )
            dropped = await store().drop_last_batch(
                docs.session_id, expected_count=len(records)
            )
        except BatchConflict:
            return _refused(
                "Nothing undone: the document changed meanwhile. Read it again."
            )
        except Exception as exc:  # noqa: BLE001 - a store failure is a tool result
            reraise_run_stop(exc)
            logger.exception(
                "[WORD_TEMPLATE][TOOL] session=%s undo failed", docs.session_id
            )
            return _tool_error(UNAVAILABLE)
        if dropped is None:
            return _ok("Nothing to undo: no edit was made in this session.")
        # The store dropped the snapshot with the batch: recompute the
        # document (this pod's cache usually still has it) and persist it
        # again so the preview and other replicas do not replay.
        current = await current_document(docs)
        listing = ""
        if not isinstance(current, str):
            active, records, state = current
            batches = [r.operations for r in records]
            _seen(batches)
            if batches:
                await save_snapshot(docs.session_id, active.base, batches, state.docx)
            listing = f"\n\nParts now:\n{state.parts_listing}"
        return _ok(f"Undone: {describe_batch(dropped)}.{listing}")

    @tool("select_template", response_format="content_and_artifact")
    async def select_template(label: str) -> tuple[str, ToolInvocationResult]:
        """Select which of this agent's Word templates this session uses.
        Only call it AFTER the collaborator confirmed the template you
        proposed (or named it themselves) - never on your own guess. label:
        one of the template names in the system prompt, exactly."""
        if not docs.session_id:
            return _tool_error("No active session.")
        match = next(
            (e for e in docs.library if normalized(e.label) == normalized(label)),
            None,
        )
        if match is None:
            known = ", ".join(f'"{e.label}"' for e in docs.library)
            return _refused(
                f'"{label}" is not one of the templates; nothing was selected. The '
                f"names are: {known}."
            )
        target = BaseRef("template", str(match.template_key))
        state = await store().get_session(docs.session_id)
        current_base = state.base if state is not None else None
        if (
            state is not None
            and state.pinned_at is not None
            and state.batch_count
            and current_base != target
        ):
            current = (
                docs.entry(current_base.ref)
                if current_base and current_base.kind == "template"
                else None
            )
            name = (
                f'"{current.label}"'
                if current
                else "an attached file"
                if current_base and current_base.kind == "attachment"
                else "another template"
            )
            return _refused(
                f'Cannot switch to "{match.label}": this session\'s document is '
                f"already being written with {name}. Changing it means starting "
                "over: only with the collaborator's explicit agreement, undo every "
                "edit (undo_last_edit until none is left) and select again, or "
                "start a new conversation."
            )
        try:
            await store().select_base(
                docs.session_id,
                target,
                docs.writer,
                expected_count=state.batch_count if state is not None else 0,
            )
        except BatchConflict:
            return _refused(
                "Nothing changed: the document was edited at the same time. Read it "
                "again before choosing its base."
            )
        return _ok(
            f'Template "{match.label}" selected for this session. Read the parts '
            "you will fill (read_template) before editing them."
        )

    @tool("use_attached_document", response_format="content_and_artifact")
    async def use_attached_document(
        attachment: str,
    ) -> tuple[str, ToolInvocationResult]:
        """Make a Word file attached in this conversation the BASE of the
        document: from then on the document is that file plus your edits,
        and it is what the collaborator downloads. Only call it when that
        file IS the document to deliver (an earlier version to update, the
        form to fill) and the collaborator asked for it or what they said
        shows it - never on a guess. A file that only feeds the content
        (needs, notes, minutes) stays a source. Switching the base is
        confirmed by the collaborator through the platform's approval step:
        call it directly, without asking them to confirm in your reply first.
        An attached file you do not make the base stays a source of
        information.

        attachment: its id from the WORD FILES ATTACHED list in the system
        prompt (e.g. "doc1")."""
        if not docs.session_id:
            return _tool_error("No active session.")
        attachments = await docs.attachments()
        match = next(
            (
                a
                for a in attachments
                if _norm_id(a.attachment_id) == _norm_id(attachment)
            ),
            None,
        )
        if match is None:
            known = ", ".join(
                f'{a.attachment_id} ("{a.filename}")' for a in attachments
            )
            return _refused(
                f'"{attachment}" is not an attached Word file; nothing changed. '
                + (
                    f"Attached Word files: {known}."
                    if attachments
                    else "No Word file is attached in this conversation."
                )
            )
        target = BaseRef("attachment", match.attachment_id)
        state = await store().get_session(docs.session_id)
        current_base = state.base if state is not None else None
        if (
            state is not None
            and state.pinned_at is not None
            and state.batch_count
            and current_base != target
        ):
            return _refused(
                f"Cannot make {match.attachment_id} the document's base: the "
                f"document already has {state.batch_count} edit(s) on another base, "
                "and switching means starting over without them. Only do it if the "
                "collaborator explicitly agrees to start over: then undo every edit "
                "(undo_last_edit with collaborator_asked set to true, until none "
                "is left) and call use_attached_document "
                "again."
            )
        batches = (
            await store().list_batches(docs.session_id)
            if current_base == target
            else []
        )
        # Read it before selecting it: an unreadable file is never made the base.
        try:
            doc_state = await docs.state(target, batches)
        except BaseUnavailable:
            return _tool_error(
                "The attached file could not be loaded right now; nothing changed."
            )
        except Exception:  # noqa: BLE001 - python-docx raises many types on a malformed file
            logger.warning(
                "[WORD_TEMPLATE][TOOL] session=%s attachment %s unreadable",
                docs.session_id,
                match.attachment_id,
                exc_info=True,
            )
            return _refused(
                f"{match.attachment_id} cannot be used as the document's base: its "
                "content could not be read. Nothing changed."
            )
        try:
            await store().select_base(
                docs.session_id,
                target,
                docs.writer,
                expected_count=state.batch_count if state is not None else 0,
            )
        except BatchConflict:
            return _refused(
                "Nothing changed: the document was edited at the same time. Read it "
                "again before choosing its base."
            )
        _seen(batches)
        return _ok(
            f'The attached file "{match.filename}" ({match.attachment_id}) is now '
            "the base of this conversation's document. Read the parts you will "
            "change (read_template) before editing them.\n\nDocument parts:\n"
            f"{doc_state.parts_listing}"
        )

    tools: list[BaseTool] = [
        read_template,
        edit_document,
        undo_last_edit,
        remove_unused_template_parts,
        use_attached_document,
    ]
    if len(docs.library) > 1:
        tools.append(select_template)
    return tools
