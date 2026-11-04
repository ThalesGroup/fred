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

"""The ReAct middleware: the prompt overlay per model call, the template
analysis on first use, and the checks of each model step (guards, a trial
before the approval gate, no unsaved or unfinished claim in an answer).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import nullcontext
from datetime import date
from typing import Any

from fred_sdk.contracts.capability import (
    CapabilityContext,
    EmptyModel,
)
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy.exc import SQLAlchemyError

from fred_capability_word_template.analysis import (
    TemplateAnalysis,
    fallback_analysis_text,
    render_analysis,
    run_analysis,
)
from fred_capability_word_template.check import (
    CHECKS,
    batch_check_basis,
    cached_check_basis,
    document_check,
    fixed_texts,
    stored_analysis,
)
from fred_capability_word_template.config import (
    WordTemplateConfig,
)
from fred_capability_word_template.docmap import (
    DocMap,
    PartCheck,
    build_map,
    chapter_of,
    render_map,
    render_parts,
)
from fred_capability_word_template.documents import (
    CLEANUP_TOOL,
    EDIT_TOOL,
    PART_NOW,
    SHIFTED,
    SHOWN,
    UNDO_TOOL,
    Active,
    BaseDoc,
    DocState,
    Documents,
    Lru,
    batch_addresses,
    chapters_of,
    current_document,
    part_ids_of,
    rewritten_addresses,
    try_batch,
    written_body_addresses,
)
from fred_capability_word_template.images import (
    images_fragment,
    session_images,
)
from fred_capability_word_template.prompt import (
    ENGINE_PRINCIPLES,
    FIXED_OUTLINE,
    NO_BASE_AVAILABLE,
    analysis_fragment,
    attachments_fragment,
    collaborator_edits_fragment,
    done_fragment,
    parts_fragment,
    selected_fragment,
    template_selection_fragment,
)
from fred_capability_word_template.session_document import (
    BaseUnavailable,
)
from fred_capability_word_template.store import (
    AttachmentInfo,
    BaseRef,
    BatchRecord,
    ImageInfo,
    get_word_template_store,
)

logger = logging.getLogger(__name__)
# A failed analysis on first use is retried at most this often per process.
_ANALYSIS_RETRY_SECONDS = 600.0
# The first-use analysis runs inside a user's model call: it never holds the
# turn longer than this (then the turn goes on with the fallback text).
_ANALYSIS_TIMEOUT_SECONDS = 60.0
# When the first-use analysis of a base (by sha256) last failed (monotonic
# time): retried at most every _ANALYSIS_RETRY_SECONDS. Pod-local (one per
# replica): another replica may retry sooner, which only costs one more call.
_ANALYSIS_FAILURES: dict[str, float] = {}
# One first-use analysis per base sha256 at a time IN THIS POD (single
# flight); another replica may run its own, the cache write is idempotent.
# One small lock per base ever analysed here.
_ANALYSIS_LOCKS: dict[str, asyncio.Lock] = {}
# The base's fixed wording per (base sha256, "fixed"), from its analysis.
_FIXED: Lru[tuple[str, str], frozenset[str]] = Lru(64)
# Why a planned edit_document is refused, per (session, tool call id), found
# when the model proposed it: the approval gate skips it and the tool call
# returns it. Read in the same step as it is written, so in the same pod.
PREFLIGHT: Lru[tuple[str | None, str], str] = Lru(1024)


class WordTemplateMiddleware(AgentMiddleware):
    """The ReAct-only half: the per-model-call prompt overlay, and the
    template analysis on first use (it needs the turn's chat model, which
    only a model call carries)."""

    def __init__(self, ctx: CapabilityContext[WordTemplateConfig, EmptyModel]) -> None:
        super().__init__()
        self._docs = Documents(ctx)

    @staticmethod
    def _recently_failed(key: str) -> bool:
        failed_at = _ANALYSIS_FAILURES.get(key)
        return (
            failed_at is not None
            and time.monotonic() - failed_at < _ANALYSIS_RETRY_SECONDS
        )

    async def _analysis(self, active: Active, model: Any) -> TemplateAnalysis | None:
        """The base's analysis, cached per sha256 of its bytes: identical
        bytes are analysed once, whether a template or an attachment. None
        when there is none (the map alone is used)."""
        if active.entry is not None and active.entry.analysis is not None:
            return active.entry.analysis
        try:
            base = await self._docs.base_doc(active.base)
        except BaseUnavailable:
            return None
        key = base.sha256
        cached = await stored_analysis(key)
        if cached is not None:
            return cached
        if model is None or self._recently_failed(key):
            return None
        # Single flight per base in this pod: concurrent first turns wait for
        # one analysis instead of each running their own.
        lock = _ANALYSIS_LOCKS.setdefault(key, asyncio.Lock())
        async with lock:
            # Re-check: the turn holding the lock, or another replica, may
            # have stored the analysis (or failed) meanwhile.
            cached = await stored_analysis(key)
            if cached is not None:
                return cached
            if self._recently_failed(key):
                return None
            return await self._run_analysis(base, model)

    async def _run_analysis(self, base: BaseDoc, model: Any) -> TemplateAnalysis | None:
        key = base.sha256
        started = time.monotonic()
        try:
            template_map, listing = await asyncio.to_thread(_blank_map, base.docx)
            started = time.monotonic()
            # Same metric as every model call of a turn (Grafana's LLM
            # latency), told apart by its `operation` dim; status=error is
            # recorded on failure or timeout.
            metrics = self._docs.metrics
            timer = (
                metrics.timer(
                    "llm.call_latency_ms",
                    dims={
                        "agent_id": self._docs.writer.agent_instance_id,
                        "operation": "word_template_analysis",
                        "model_name": _model_name(model),
                    },
                )
                if metrics is not None
                else nullcontext()
            )
            with timer:
                analysis = await asyncio.wait_for(
                    run_analysis(model, template_map, listing),
                    timeout=_ANALYSIS_TIMEOUT_SECONDS,
                )
        except TimeoutError:
            _ANALYSIS_FAILURES[key] = time.monotonic()
            logger.warning(
                "[WORD_TEMPLATE] analysis of base %s timed out after %.0fs; using the map only",
                key,
                time.monotonic() - started,
            )
            return None
        except Exception:  # noqa: BLE001 - any model or provider failure falls back to the map
            _ANALYSIS_FAILURES[key] = time.monotonic()
            logger.warning(
                "[WORD_TEMPLATE] analysis of base %s failed after %.1fs; using the map only",
                key,
                time.monotonic() - started,
                exc_info=True,
            )
            return None
        _ANALYSIS_FAILURES.pop(key, None)
        logger.info(
            "[WORD_TEMPLATE] analysed base %s in %.1fs (%d parts)",
            key,
            time.monotonic() - started,
            len(analysis.parts),
        )
        try:
            await get_word_template_store().put_analysis(
                key, analysis.model_dump_json()
            )
        except (SQLAlchemyError, OSError):
            logger.exception("[WORD_TEMPLATE] failed to cache the analysis")
        return analysis

    async def _document_check(
        self, active: Active, analysis: TemplateAnalysis | None, state: DocState
    ) -> list[PartCheck] | None:
        """The check of every part, or None when the base cannot be read."""
        try:
            base_doc = await self._docs.base_doc(active.base)
        except BaseUnavailable:
            return None
        key = (len(state.docx), hash(state.docx), base_doc.sha256, analysis is not None)
        cached = CHECKS.get(key)
        if cached is not None:
            return cached
        try:
            basis = await cached_check_basis(base_doc, analysis)
            result = await asyncio.to_thread(document_check, state.docx, basis)
        except Exception:  # noqa: BLE001 - a progress hint must never break the prompt
            logger.warning(
                "[WORD_TEMPLATE] failed to check the document", exc_info=True
            )
            return None
        CHECKS.put(key, result)
        return result

    async def _document_view(
        self, base: BaseRef
    ) -> tuple[list[BatchRecord], DocState | None]:
        """The session's edits and the document state (None if it failed)."""
        docs = self._docs
        records: list[BatchRecord] = []
        if docs.session_id:
            try:
                records = await get_word_template_store().list_batch_records(
                    docs.session_id
                )
            except (SQLAlchemyError, OSError):
                logger.exception("[WORD_TEMPLATE] failed to list the session's edits")
        batches = [r.operations for r in records]
        try:
            return records, await docs.state(base, batches)
        except Exception:  # noqa: BLE001 - loading or replaying the base must not break the prompt
            logger.exception("[WORD_TEMPLATE] failed to build the document state")
            return records, None

    async def _attachments(self) -> list[AttachmentInfo]:
        try:
            return await self._docs.attachments()
        except (SQLAlchemyError, OSError):
            logger.exception("[WORD_TEMPLATE] failed to list the session's attachments")
            return []

    async def _images(self, attachments: Sequence[AttachmentInfo]) -> list[ImageInfo]:
        """The session's images (backfilling the pictures of attachments
        stored before images existed). Best effort: none on failure."""
        if not self._docs.session_id:
            return []
        try:
            return await session_images(self._docs.session_id, attachments)
        except (SQLAlchemyError, OSError):
            logger.exception("[WORD_TEMPLATE] failed to list the session's images")
            return []

    async def _fragments(self, model: Any) -> list[str]:
        docs = self._docs
        try:
            active, attachments = await asyncio.gather(
                docs.active(), self._attachments()
            )
        except (SQLAlchemyError, OSError):
            logger.exception("[WORD_TEMPLATE] failed to resolve the session's base")
            return [ENGINE_PRINCIPLES]
        has_library = bool(docs.library)
        listed = (
            [
                attachments_fragment(
                    attachments,
                    active.base if active else None,
                    has_library=has_library,
                )
            ]
            if attachments
            else []
        )
        if active is None:
            if not has_library and not attachments:
                return [NO_BASE_AVAILABLE]
            selection = (
                [template_selection_fragment(docs.library)]
                if len(docs.library) > 1
                else []
            )
            return [*selection, *listed]
        # The model has no clock: a version date or "today" comes from here.
        fragments = [ENGINE_PRINCIPLES, f"TODAY'S DATE: {date.today().isoformat()}"]
        if active.label:
            fragments.append(
                selected_fragment(active.label, several=len(docs.library) > 1)
            )
        fragments.extend(listed)
        # Independent: the analysis and the document. Both handle their own
        # errors (fallback text / no parts listing).
        analysis, (records, state), images = await asyncio.gather(
            self._analysis(active, model),
            self._document_view(active.base),
            self._images(attachments),
        )
        fragments.append(
            analysis_fragment(
                render_analysis(analysis)
                if analysis is not None
                else fallback_analysis_text()
            )
        )
        basis = await batch_check_basis(self._docs, active)
        if basis is not None and basis.fixed_outline:
            fragments.append(FIXED_OUTLINE)
        listed_images = images_fragment(images)
        if listed_images is not None:
            fragments.append(listed_images)
        if state is not None:
            checks = await self._document_check(active, analysis, state)
            fragments.append(parts_fragment(state.parts_listing, checks))
        fragments.append(done_fragment(records))
        collaborator = collaborator_edits_fragment(records)
        if collaborator is not None:
            fragments.append(collaborator)
        return fragments

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """The prompt overlay, then two checks of the model's response: an
        edit the engine would refuse is planned again before it runs or
        reaches the approval gate, and a final answer is asked again when
        it repeats a tool message or follows an edit that was not applied."""
        overlay = "\n\n".join(await self._fragments(getattr(request, "model", None)))
        base = request.system_prompt or ""
        merged = f"{base}\n\n{overlay}" if base else overlay

        async def ask(*notes: str) -> ModelResponse:
            prompt = "\n\n".join((merged, *notes))
            return await handler(
                request.override(system_message=SystemMessage(content=prompt))
            )

        history = _messages_of(getattr(request, "state", None)) or (
            getattr(request, "messages", None) or []
        )
        response = await ask()
        refusals = await self._planned_refusals(history, response)
        if refusals:
            # Asked once more; whatever is still refused then is answered by
            # its tool call, without reaching the approval gate.
            logger.info(
                "[WORD_TEMPLATE] session=%s planned edit would be refused; asking again",
                self._docs.session_id,
            )
            response = await ask(_replan_note(refusals.values()))
            refusals = await self._planned_refusals(history, response)
            if refusals and set(refusals.values()) == {_ONE_PART_PER_TURN}:
                # Another part again: each refused call spends the turn's
                # tool-call budget, so the turn ends here with the answer.
                response = await ask(_TURN_DONE_NOTE)
                refusals = await self._planned_refusals(history, response)
            for call_id, refusal in refusals.items():
                PREFLIGHT.put((self._docs.session_id, call_id), refusal)
        notes: list[str] = []
        if _echoed_answer(response) is not None:
            notes.append(_ECHO_RETRY_NOTE)
        if _final_answer(response) is not None:
            unsaved = _unsaved_edit(history)
            if unsaved is not None:
                notes.append(_unsaved_note(unsaved))
            elif unfinished := await self._unfinished(history):
                notes.append(_unfinished_note(unfinished))
        if not notes:
            return response
        logger.warning(
            "[WORD_TEMPLATE] session=%s answer asked again: %d note(s)",
            self._docs.session_id,
            len(notes),
        )
        retried = await ask(*notes)
        if _echoed_answer(retried) is None:
            return retried
        logger.warning(
            "[WORD_TEMPLATE] session=%s retried answer still repeated a tool "
            "message; replaced with a neutral sentence",
            self._docs.session_id,
        )
        return _with_answer(
            retried, _neutral_answer(getattr(request, "messages", None) or [])
        )

    async def _unfinished(self, history: Sequence[Any]) -> list[str]:
        """The chapters written in this turn that still hold the template's
        own text (guidance, samples), per the document check."""
        written = _chapters_written_this_turn({"messages": history}, "") - {"?"}
        if not written:
            return []
        try:
            active = await self._docs.active()
            if active is None:
                return []
            _records, state = await self._document_view(active.base)
            analysis = await self._analysis(active, None)
        except (SQLAlchemyError, OSError):
            return []
        checks = await self._document_check(active, analysis, state) if state else None
        return sorted(
            {
                chapter_of(c.part_id)
                for c in checks or []
                if chapter_of(c.part_id) in written
                and any(left.kind == "template" for left in c.leftovers)
            }
        )

    async def _planned_refusals(
        self, history: Sequence[Any], response: Any
    ) -> dict[str, str]:
        """Why each edit_document the response plans would be refused, by
        tool call id: the guards, then a trial of the batch (nothing stored)."""
        planned = _planned_step(response)
        if planned is None:
            return {}
        state = {"messages": [*history, planned]}
        refusals: dict[str, str] = {}
        for call in planned.tool_calls:
            if call.get("name") != EDIT_TOOL:
                continue
            refusal = await self._refusal(state, call, trial=True)
            if refusal is not None:
                refusals[str(call.get("id") or "")] = refusal
        return refusals

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """An edit_document runs only when the guards let it through, or the
        refusal found when it was planned is returned. A refused call gets
        its own result (same tool_call id), so calls and results stay
        paired."""
        call = request.tool_call
        call_id = str(call.get("id") or "")
        if call.get("name") == UNDO_TOOL:
            args = call.get("args") or {}
            asked = isinstance(args, Mapping) and args.get("collaborator_asked") is True
            if asked or _edits_applied_this_turn(request.state, call_id) > 0:
                return await handler(request)
            return ToolMessage(
                content=_UNDO_EARLIER_TURN, tool_call_id=call_id, name=UNDO_TOOL
            )
        if call.get("name") != EDIT_TOOL:
            return await handler(request)
        refusal = PREFLIGHT.pop((self._docs.session_id, call_id))
        if refusal is None:
            refusal = await self._refusal(request.state, call, trial=False)
        if refusal is None:
            return await handler(request)
        logger.info(
            "[WORD_TEMPLATE] session=%s refused an edit_document: %s",
            self._docs.session_id,
            refusal.split(":", 1)[0],
        )
        # A plain (non-error) result: an error would replace the model's own
        # answer to the collaborator, and this refusal is for the model only.
        return ToolMessage(content=refusal, tool_call_id=call_id, name=EDIT_TOOL)

    async def _refusal(
        self, state: Any, call: Mapping[str, Any], *, trial: bool
    ) -> str | None:
        """Why an edit_document call is refused, or None. The guards: the
        first edit of its step, on parts the model has seen as they are now,
        within the content rules. With ``trial``, the batch is also run
        without storing it (the tool runs it anyway when it is called)."""
        call_id = str(call.get("id") or "")
        if _later_edit_of_its_step(state, call_id):
            return _ONE_EDIT_AT_A_TIME
        known = _known_parts(state, call_id)
        if known is not None and not known:
            return _read_first()
        args = call.get("args")
        args = args if isinstance(args, Mapping) else {}
        operations = args.get("operations")
        current = await current_document(self._docs)
        if isinstance(current, str):
            return None  # the tool reports a missing or unreadable document
        active, records, doc_state = current
        doc_map = await asyncio.to_thread(build_map, doc_state.docx)
        if known is not None:
            unread = set(part_ids_of(doc_map, batch_addresses(operations))) - known
            if unread:
                return _read_first(sorted(unread))
        refusal = await self._content_refusal(state, call, active, doc_map)
        if refusal is not None or not trial or not isinstance(operations, list):
            return refusal
        basis = await batch_check_basis(self._docs, active)
        try:
            tried = await try_batch(
                self._docs,
                active,
                records,
                doc_state,
                operations,
                changes_template=args.get("changes_template") is True,
                fixed_outline=basis is not None and basis.fixed_outline,
            )
        except BaseUnavailable:
            return None
        return tried if isinstance(tried, str) else None

    async def _content_refusal(
        self, state: Any, call: Mapping[str, Any], active: Active, doc_map: DocMap
    ) -> str | None:
        """Two rules on the content a batch rewrites:
        - written content (write / insert_after in the body) goes into one
          part per turn, so the collaborator reviews each part before the
          next; filling fields and cells (forms, cover page, headers) stays
          free;
        - rewriting or removing the template's fixed wording needs
          `changes_template`, which sends the batch to the collaborator's
          approval."""
        args = call.get("args") or {}
        operations = args.get("operations")
        written = written_body_addresses(operations)
        if written:
            targets = set(chapters_of(part_ids_of(doc_map, written)))
            earlier = _chapters_written_this_turn(state, str(call.get("id") or ""))
            if len(targets) > 1 or (earlier and not targets <= earlier):
                return _ONE_PART_PER_TURN
        rewritten = rewritten_addresses(operations)
        if not rewritten or args.get("changes_template") is True:
            return None
        try:
            fixed = await self._fixed_texts(active)
        except Exception:  # noqa: BLE001 - the tool itself reports an unreadable document
            return None
        if fixed and _touches_texts(doc_map, rewritten, fixed):
            return _FIXED_WORDING
        return None

    async def _fixed_texts(self, active: Active) -> frozenset[str]:
        """The base's fixed wording per its analysis (cached); none without one."""
        analysis = await self._analysis(active, None)
        if analysis is None:
            return frozenset()
        base = await self._docs.base_doc(active.base)
        key = (base.sha256, "fixed")
        cached = _FIXED.get(key)
        if cached is None:
            cached = await asyncio.to_thread(
                lambda: fixed_texts(build_map(base.docx), analysis)
            )
            _FIXED.put(key, cached)
        return cached


_UNDO_EARLIER_TURN = (
    "Nothing undone: no edit was applied in this turn, so the last edit is one "
    "the collaborator has already seen. If the collaborator asked to go back "
    "(cancel, restore what was there before), call undo_last_edit again with "
    "collaborator_asked set to true: they confirm it. Otherwise a refused "
    "batch changed nothing: fix it and send it again, and never rewrite the "
    "previous text from memory."
)
_ONE_EDIT_AT_A_TIME = (
    "Not applied: only one edit_document at a time. This call was sent in the "
    "same step as another edit_document, so it was refused. Wait for that "
    "edit's result, read the parts again if needed, then send the next batch."
)


def _read_first(parts: Sequence[str] = ()) -> str:
    what = (
        f"part {', '.join(parts)} has" if parts else "the parts you are changing have"
    )
    return (
        f"Not applied: read before you edit. {what} not been shown to you since "
        "the template or base file was chosen, or since an edit or an undo "
        "shifted the addresses, so these addresses may be wrong. Read them "
        "(read_template), then send the batch."
    )


_ONE_PART_PER_TURN = (
    "Not applied: written content goes into one part per turn. Write only the "
    "part you started (or the next one), show the collaborator what you wrote, "
    "and wait for their reply before writing another part. Filling fields or "
    "table cells is not limited."
)
_TURN_DONE_NOTE = (
    "NOTE: your previous step was not run: this turn has already written a "
    "part, and the next part waits for the collaborator's reply. Make no "
    "other edit in this turn: answer the collaborator now, showing what you "
    "wrote, and stop."
)
_FIXED_WORDING = (
    "Not applied: this batch rewrites fixed wording of the template (text "
    "the template means to keep as it is). Keep it, and write only in the "
    "places meant to be filled; replace_text may still adjust a detail inside "
    "a sentence. Change fixed wording only if the collaborator asked for it: "
    "then tell them exactly what you will change and send the batch again "
    "with changes_template set to true, for their approval."
)


def _touches_texts(
    doc_map: DocMap, ranges: Sequence[tuple[str, str]], texts: frozenset[str]
) -> bool:
    """Whether a paragraph inside one of ``ranges`` holds one of ``texts``."""
    order = {e.address: i for i, e in enumerate(doc_map.elements)}
    for first, last in ranges:
        a, b = order.get(first), order.get(last)
        if a is None or b is None:
            continue
        span = doc_map.elements[min(a, b) : max(a, b) + 1]
        prefixes = tuple(f"{e.address}." for e in span)
        own = {e.address for e in span}
        for e in doc_map.elements:
            if (
                e.kind == "paragraph"
                and e.heading_level is None
                and (e.address in own or e.address.startswith(prefixes))
                and e.text.strip() in texts
            ):
                return True
    return False


def _turn_before(state: Any, call_id: str) -> list[Any]:
    """The messages of this turn (since the collaborator's last message)
    before the step that makes ``call_id``."""
    messages = list(_messages_of(state))
    end = next(
        (
            i
            for i, m in enumerate(messages)
            if isinstance(m, AIMessage)
            and any(c.get("id") == call_id for c in m.tool_calls or [])
        ),
        len(messages),
    )
    start = max(
        (i for i, m in enumerate(messages[:end]) if isinstance(m, HumanMessage)),
        default=-1,
    )
    return messages[start + 1 : end]


def _edits_applied_this_turn(state: Any, call_id: str) -> int:
    """Batches applied in this turn and not undone since: the ones the
    model may undo on its own."""
    messages = _turn_before(state, call_id)
    tool_of = {
        c.get("id"): c.get("name")
        for m in messages
        if isinstance(m, AIMessage)
        for c in m.tool_calls or []
    }
    count = 0
    for m in messages:
        content = m.content if isinstance(m, ToolMessage) else None
        if not isinstance(content, str):
            continue
        tool = tool_of.get(m.tool_call_id)
        if tool in (EDIT_TOOL, CLEANUP_TOOL) and content.startswith("Applied"):
            count += 1
        elif tool == UNDO_TOOL and content.startswith("Undone: "):
            count -= 1
    return count


def _chapters_written_this_turn(state: Any, call_id: str) -> set[str]:
    """The chapters already written in this turn (since the collaborator's
    last message), read from the replies of applied batches that wrote
    content. An applied writing batch whose reply lists no part counts as
    unknown."""
    messages = _turn_before(state, call_id)
    writing = {
        c.get("id")
        for m in messages
        if isinstance(m, AIMessage)
        for c in m.tool_calls or []
        if c.get("name") == EDIT_TOOL
        and written_body_addresses((c.get("args") or {}).get("operations"))
    }
    parts: set[str] = set()
    for m in messages:
        if not isinstance(m, ToolMessage) or m.tool_call_id not in writing:
            continue
        content = m.content if isinstance(m.content, str) else ""
        if content.startswith("Applied"):
            parts |= set(chapters_of(PART_NOW.findall(content))) or {"?"}
    return parts


_BASE_CHANGES = ("select_template", "use_attached_document")
_ADDRESSES_RESET = re.compile(
    rf"selected for this session\.|is now the base|^Undone: |\n{SHIFTED}"
)


def _messages_of(state: Any) -> Sequence[Any]:
    if isinstance(state, Mapping):
        return state.get("messages") or ()
    return getattr(state, "messages", None) or ()


def _later_edit_of_its_step(state: Any, call_id: str) -> bool:
    """Whether ``call_id`` is an edit_document call that is not the first
    edit_document of the model message that issued it."""
    if not call_id:
        return False
    for message in reversed(_messages_of(state)):
        if not isinstance(message, AIMessage):
            continue
        calls = message.tool_calls or []
        if not any(c.get("id") == call_id for c in calls):
            continue
        edits = [c.get("id") for c in calls if c.get("name") == EDIT_TOOL]
        return bool(edits) and edits[0] != call_id
    return False


def _known_parts(state: Any, call_id: str) -> frozenset[str] | None:
    """The parts the model had seen as they are now when it planned
    ``call_id``: shown by a read or an applied edit's reply, since the last
    change of addresses (a new base, a structural edit, an undo). Results of
    the same step do not count: they had not run when the call was planned.
    None for a call missing from the history: nothing to judge it on."""
    known: set[str] = set()
    for message in _messages_of(state):
        if isinstance(message, AIMessage) and any(
            c.get("id") == call_id for c in message.tool_calls or []
        ):
            return frozenset(known)
        if not isinstance(message, ToolMessage):
            continue
        content = message.content if isinstance(message.content, str) else ""
        if message.name in (
            *_BASE_CHANGES,
            EDIT_TOOL,
            UNDO_TOOL,
            CLEANUP_TOOL,
        ) and _ADDRESSES_RESET.search(content):
            known.clear()
        if message.name in ("read_template", EDIT_TOOL):
            known.update(SHOWN.findall(content))
    return None


def _planned_step(response: Any) -> AIMessage | None:
    """The model message of a response that calls tools, None otherwise."""
    if isinstance(response, AIMessage):
        message: Any = response
    elif isinstance(response, ModelResponse):
        message = next(
            (m for m in reversed(response.result) if isinstance(m, AIMessage)), None
        )
    else:
        return None
    return message if message is not None and message.tool_calls else None


def _unsaved_edit(messages: Sequence[Any]) -> str | None:
    """Why the last edit_document of the turn (since the collaborator's last
    message) was not applied, or None when it was, or when there is none."""
    names = {
        c.get("id"): c.get("name")
        for m in messages
        if isinstance(m, AIMessage)
        for c in m.tool_calls or []
    }
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return None
        if not isinstance(message, ToolMessage):
            continue
        if (message.name or names.get(message.tool_call_id)) != EDIT_TOOL:
            continue
        text = _message_text(message).strip()
        if text.startswith("Applied"):
            return None
        return text.splitlines()[0] if text else "no result"
    return None


def _unsaved_note(reason: str) -> str:
    return (
        "NOTE: the last edit_document of this turn was not applied "
        f"({reason}), so the document does not hold that content. Do not tell "
        "the collaborator it is in the document: say plainly what was not "
        "saved, and what they can do next."
    )


def _unfinished_note(chapters: Sequence[str]) -> str:
    return (
        f"NOTE: part {', '.join(chapters)}, written in this turn, still holds "
        "text of the template itself (instructions or sample content), as the "
        "DOCUMENT CHECK shows. It is not complete: do not say it is up to "
        "date. Say plainly what is left, or replace it."
    )


def _replan_note(refusals: Iterable[str]) -> str:
    return (
        "NOTE: your previous step was not run: the engine would refuse its "
        "edit_document, and nothing in the document changed:\n- "
        + "\n- ".join(dict.fromkeys(refusals))
        + "\nPlan the step again with this in mind."
    )


# Texts only this capability's tools produce (edit_document, read_template,
# undo_last_edit). One of them in an answer means the model is relaying a
# tool message to the collaborator.
_OPS = r"(?:set_text|replace_text|write|insert_after|repeat|remove)"
_INTERNAL_SIGNATURES: tuple[str, ...] = (
    r"Nothing was applied",
    r"send the whole batch again",
    r"does not exist \(the document has",
    r"Applied \d+ operation\(s\) as edit #\d+",
    r"Addresses after a structural change have shifted",
    r"\(current state\):",
    r"\bParts now:",
    r"\bCHECK of part \S+ \(",
    r"\bDOCUMENT CHECK \(",
    rf"\boperation \d+ \({_OPS}\)",
    r"\boperations \d+ and \d+ overlap",
    r"only one edit_document at a time",
    r"read before you edit",
    r"is not a part id of this document",
    rf"Undone: {_OPS}\b",
)
_INTERNAL_MESSAGE = re.compile("|".join(_INTERNAL_SIGNATURES), re.IGNORECASE)

_ECHO_RETRY_NOTE = (
    "NOTE: your previous draft of this answer repeated an internal tool "
    "message, which the collaborator must never see. Answer again, in the "
    "collaborator's language: say plainly what was done to their document, or "
    "what still blocks it. No tool message, address, operation or tool name."
)

_NEUTRAL_ANSWER = {
    "fr": (
        "Je n'ai pas pu rédiger ma réponse. Consultez l'aperçu du document et "
        "dites-moi comment poursuivre."
    ),
    "en": (
        "I could not write my answer. Please check the document preview and "
        "tell me how to continue."
    ),
}

# Frequent short words of each language, to tell them apart.
_FRENCH = (
    "le la les un une des du de et est je tu vous nous il elle on pour que qui "
    "pas dans sur avec ce cette mais ou au aux mets met fais peux"
)
_ENGLISH = (
    "the an and is are i you we it to of for that this with in please can do "
    "not what my your"
)
_FRENCH_WORDS = frozenset(_FRENCH.split())
_ENGLISH_WORDS = frozenset(_ENGLISH.split())


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block if isinstance(block, str) else str(block.get("text") or "")
            for block in content
            if isinstance(block, str | dict)
        )
    return ""


def _final_answer(response: Any) -> AIMessage | None:
    """The answer of a model response that ends the turn (an AIMessage
    without tool calls), None otherwise."""
    if isinstance(response, AIMessage):
        message: Any = response
    elif isinstance(response, ModelResponse):
        message = next(
            (m for m in reversed(response.result) if isinstance(m, AIMessage)), None
        )
    else:
        return None
    if message is None or message.tool_calls:
        return None
    return message


def _echoed_answer(response: Any) -> AIMessage | None:
    """The final answer if it repeats an internal tool message."""
    answer = _final_answer(response)
    if answer is None or not _INTERNAL_MESSAGE.search(_message_text(answer)):
        return None
    return answer


def _with_answer(response: Any, text: str) -> Any:
    answer = _final_answer(response)
    if answer is None:
        return response
    replaced = answer.model_copy(update={"content": text})
    if isinstance(response, AIMessage):
        return replaced
    return ModelResponse(
        result=[replaced if m is answer else m for m in response.result],
        structured_response=response.structured_response,
    )


def _collaborator_language(messages: Sequence[Any]) -> str:
    """French ("fr") when the collaborator's last message reads so, else "en":
    English is the default when the language cannot be determined."""
    last = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    words = re.findall(r"[a-zà-ÿ']+", _message_text(last).lower()) if last else []
    french = sum(w in _FRENCH_WORDS for w in words) + sum(
        any(c in "éèêàçùâîôûœ" for c in w) for w in words
    )
    english = sum(w in _ENGLISH_WORDS for w in words)
    return "fr" if french > english else "en"


def _neutral_answer(messages: Sequence[Any]) -> str:
    return _NEUTRAL_ANSWER[_collaborator_language(messages)]


def _model_name(model: Any) -> str | None:
    for attr in ("model_name", "model", "deployment_name"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def _blank_map(template: bytes) -> tuple[str, str]:
    doc_map = build_map(template)
    return render_map(doc_map), render_parts(doc_map)
