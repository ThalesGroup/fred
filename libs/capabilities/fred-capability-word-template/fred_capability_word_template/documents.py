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

"""The session's document: its base, the replayed operation log (pod-local
caches), the trial of a model batch, and what a batch addresses.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fred_sdk.contracts.capability import (
    CapabilityContext,
    EmptyModel,
)
from fred_sdk.contracts.runtime import unwrap_run_stop_error

from fred_capability_word_template.config import (
    WordTemplateConfig,
    WordTemplateEntry,
)
from fred_capability_word_template.docmap import (
    MAP_NOTE_RE,
    DocMap,
    build_map,
    chapter_of,
    parts,
    render_parts,
)
from fred_capability_word_template.images import (
    images_for,
)
from fred_capability_word_template.operations import (
    TYPED_TITLE_RE,
    BatchError,
    TableSignature,
    apply_batch,
    chapters_with_template_sub_headings,
    fit_to_document,
    inspect_set_texts,
    normalized,
    parse_operation,
    template_heading_texts,
    template_sub_heading_levels,
    template_table_signatures,
)
from fred_capability_word_template.render import markdown_features
from fred_capability_word_template.session_document import (
    BaseUnavailable,
    content_sha256,
    load_base_bytes,
    log_digest,
    save_snapshot,
    session_docx,
)
from fred_capability_word_template.store import (
    AttachmentInfo,
    BaseRef,
    Batch,
    BatchRecord,
    Writer,
    get_word_template_store,
)

logger = logging.getLogger(__name__)


# --- the session's document ---------------------------------------------------------


@dataclass(frozen=True)
class Active:
    """The session's base. ``label``/``entry`` are set for a library
    template still in the library, never for an attachment."""

    base: BaseRef
    label: str | None = None
    entry: WordTemplateEntry | None = None


@dataclass(frozen=True)
class BaseDoc:
    """A base document's bytes and their sha256 (the analysis cache key)."""

    docx: bytes
    sha256: str


@dataclass(frozen=True)
class _TemplateShape:
    tables: frozenset[TableSignature]
    headings: frozenset[str]
    sub_heading_levels: frozenset[int]


def _template_shape(docx: bytes) -> _TemplateShape:
    return _TemplateShape(
        template_table_signatures(docx),
        template_heading_texts(docx),
        template_sub_heading_levels(docx),
    )


@dataclass(frozen=True)
class DocState:
    docx: bytes
    parts_listing: str


class Lru[K, V]:
    """A tiny per-process LRU (see the pod-local caches below), bounded by
    entry count and, with ``weigh``, by total weight (bytes): an attached
    file can be 20 MB, so the count alone does not bound memory."""

    def __init__(
        self,
        size: int,
        *,
        max_weight: int | None = None,
        weigh: Callable[[V], int] | None = None,
    ) -> None:
        self._size = size
        self._max_weight = max_weight
        self._weigh = weigh
        self._weight = 0
        self._items: OrderedDict[K, V] = OrderedDict()

    def _w(self, value: V) -> int:
        return self._weigh(value) if self._weigh is not None else 0

    def get(self, key: K) -> V | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def put(self, key: K, value: V) -> None:
        weight = self._w(value)
        if self._max_weight is not None and weight > self._max_weight:
            return  # too big to keep: the next miss recomputes or reads it
        old = self._items.pop(key, None)
        if old is not None:
            self._weight -= self._w(old)
        self._items[key] = value
        self._weight += weight
        while len(self._items) > self._size or (
            self._max_weight is not None and self._weight > self._max_weight
        ):
            _key, evicted = self._items.popitem(last=False)
            self._weight -= self._w(evicted)

    def pop(self, key: K) -> V | None:
        value = self._items.pop(key, None)
        if value is not None:
            self._weight -= self._w(value)
        return value

    def clear(self) -> None:
        self._items.clear()
        self._weight = 0


# Pod-local caches: each replica has its own, and a miss recomputes or reads
# Postgres, so nothing depends on them being shared.
#
# Base bytes (+ sha256) per (team, agent instance, session for an
# attachment, base identity): a template key or an attachment id never
# changes bytes.
_BASES: Lru[tuple[str | None, str | None, str | None, str], BaseDoc] = Lru(
    16, max_weight=64 * 1024 * 1024, weigh=lambda doc: len(doc.docx)
)
# Document state per (session, base sha256, log digest): read on every model
# call and tool call. Bounded memory: one docx each.
_STATES: Lru[tuple[str | None, str, str], DocState] = Lru(
    128, max_weight=256 * 1024 * 1024, weigh=lambda state: len(state.docx)
)
# Per session: a digest of the log the model last READ in this pod (a read,
# an edit's reply, a base choice, its own undo). With no mark (another
# replica read it) the model's last batch stands in for it.
SEEN: Lru[str, str] = Lru(4096)
# What a model batch must keep of the base, per base sha256: its tables (a
# copy of each) and its headings. Computed once per base in this pod.
_TEMPLATE_SHAPES: Lru[str, _TemplateShape] = Lru(64)


def state_from(docx: bytes) -> DocState:
    return DocState(docx=docx, parts_listing=render_parts(build_map(docx)))


class Documents:
    """Everything the tools and the prompt need about the session's
    document, bound to one capability context."""

    def __init__(self, ctx: CapabilityContext[WordTemplateConfig, EmptyModel]) -> None:
        identity = ctx.identity
        self.session_id = identity.session_id
        self.writer = Writer(
            user_id=identity.user_id,
            team_id=identity.team_id,
            agent_instance_id=identity.agent_instance_id,
        )
        self.library = [e for e in ctx.config.template_library or [] if e.template_key]
        self._assets = ctx.services.agent_assets
        self.metrics = ctx.services.metrics

    def entry(self, key: str) -> WordTemplateEntry | None:
        return next((e for e in self.library if e.template_key == key), None)

    def _active_for(self, base: BaseRef) -> Active:
        if base.kind == "template":
            entry = self.entry(base.ref)
            return Active(base, entry.label if entry else None, entry)
        return Active(base)

    async def active(self) -> Active | None:
        """The pinned base, else a selected attachment (the collaborator's
        explicit choice), else the only template, else the selected one."""
        state = None
        if self.session_id:
            state = await get_word_template_store().get_session(self.session_id)
        base = state.base if state is not None else None
        if state is not None and state.pinned_at is not None and base is not None:
            return self._active_for(base)
        if base is not None and base.kind == "attachment":
            return self._active_for(base)
        if len(self.library) == 1:
            return self._active_for(
                BaseRef("template", str(self.library[0].template_key))
            )
        if base is not None and self.entry(base.ref) is not None:
            return self._active_for(base)
        return None

    async def attachments(self) -> list[AttachmentInfo]:
        if not self.session_id:
            return []
        return await get_word_template_store().list_attachments(self.session_id)

    async def _fetch_template(self, key: str) -> bytes:
        if self._assets is None:
            raise BaseUnavailable("no asset service to fetch the template")
        return await self._assets.fetch(key)

    async def base_doc(self, base: BaseRef) -> BaseDoc:
        """The base's bytes and sha256 (``load_base_bytes``, cached in this
        pod). An attachment is cached by its stored sha256, so a short id
        reused after a delete never serves the old file. Raises
        ``BaseUnavailable``."""
        known_sha = await self._attachment_sha(base)
        cache_key = (
            self.writer.team_id,
            self.writer.agent_instance_id,
            self.session_id if base.kind == "attachment" else None,
            known_sha or base.identity,
        )
        cached = _BASES.get(cache_key)
        if cached is not None:
            return cached
        try:
            data = await load_base_bytes(base, self.session_id, self._fetch_template)
        except BaseUnavailable:
            logger.warning(
                "[WORD_TEMPLATE] session=%s failed to load base %s",
                self.session_id,
                base.identity,
                exc_info=True,
            )
            raise
        # Up to 20 MB to hash: off the event loop (an attachment's is stored).
        sha = known_sha or await asyncio.to_thread(content_sha256, data)
        doc = BaseDoc(data, sha)
        _BASES.put(cache_key, doc)
        return doc

    async def _attachment_sha(self, base: BaseRef) -> str | None:
        if base.kind != "attachment" or not self.session_id:
            return None
        for info in await self.attachments():
            if info.attachment_id == base.ref:
                return info.sha256
        raise BaseUnavailable(f"attachment {base.ref} not found")

    async def template_shape(self, base: BaseRef) -> _TemplateShape:
        """The base document's tables and headings (cached per sha256).
        Raises ``BaseUnavailable``."""
        doc = await self.base_doc(base)
        cached = _TEMPLATE_SHAPES.get(doc.sha256)
        if cached is None:
            # Parses the base docx: off the event loop.
            cached = await asyncio.to_thread(_template_shape, doc.docx)
            _TEMPLATE_SHAPES.put(doc.sha256, cached)
        return cached

    async def _base_bytes(self, base: BaseRef) -> bytes:
        return (await self.base_doc(base)).docx

    async def state(self, base: BaseRef, batches: Sequence[Batch]) -> DocState:
        """The document after ``batches``: this pod's cache, else the
        persisted snapshot (plus any later batch), else a full replay."""
        cache_key = await self._state_key(base, batches)
        cached = _STATES.get(cache_key)
        if cached is not None:
            return cached
        docx = await session_docx(
            self.session_id, base, batches, lambda: self._base_bytes(base)
        )
        # CPU-bound map: off the event loop that serves every turn.
        state = await asyncio.to_thread(state_from, docx)
        _STATES.put(cache_key, state)
        return state

    async def _state_key(
        self, base: BaseRef, batches: Sequence[Batch]
    ) -> tuple[str | None, str, str]:
        """Per session: short attachment and image ids only mean something
        inside one conversation; an attachment by its stored sha256 (a
        template's asset key is unique), so no base is fetched for the key."""
        content = await self._attachment_sha(base) or base.identity
        return (self.session_id, content, log_digest(base, batches))

    async def remember(
        self, base: BaseRef, batches: Sequence[Batch], state: DocState
    ) -> None:
        """Record the document just produced by an edit: in this pod's
        cache and as the session's persisted snapshot."""
        _STATES.put(await self._state_key(base, batches), state)
        if self.session_id:
            await save_snapshot(self.session_id, base, batches, state.docx)


# --- affected parts -------------------------------------------------------------------


def _top_level(doc_map: DocMap, address: str) -> str | None:
    """The top-level body block holding ``address``, ``"hf"`` for a header
    or footer, None when unknown."""
    if address[:1] in ("H", "F"):
        return "hf"
    element = doc_map.get(address)
    seen = 0
    while element is not None and seen < 50:
        seen += 1
        if element.kind == "textbox":
            anchor = (element.label or "").rsplit(" ", 1)[-1]
            element = doc_map.get(anchor)
            continue
        if not element.container:
            return element.address
        element = doc_map.get(element.container)
    return None


def part_ids_of(doc_map: DocMap, addresses: Sequence[str]) -> list[str]:
    tops = [t for a in addresses if (t := _top_level(doc_map, a))]
    order = {
        e.address: i
        for i, e in enumerate(
            e for e in doc_map.elements if e.container == "" and e.is_block
        )
    }
    found: list[str] = []
    for part in parts(doc_map):
        if part.part_id == "hf":
            hit = "hf" in tops
        else:
            first = order.get(part.first or "", -1)
            last = order.get(part.last or "", -1)
            hit = any(first <= order.get(t, -2) <= last for t in tops if t != "hf")
        if hit:
            found.append(part.part_id)
    return found


def chapters_of(part_ids: Iterable[str]) -> list[str]:
    """The chapters of parts, in order, once each: "5" for "5" and "5b"."""
    return list(dict.fromkeys(chapter_of(p) for p in part_ids))


def operation_addresses(batch: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for op in batch:
        for field in ("address", "from", "to", "before", "after"):
            value = op.get(field)
            if isinstance(value, str) and value:
                out.append(value)
    return out


UNAVAILABLE = "The Word document could not be loaded right now; try again later."


def reraise_run_stop(exc: BaseException) -> None:
    """A stopped run ends; it never reaches the model as tool text."""
    stop = unwrap_run_stop_error(exc)
    if stop is not None:
        raise stop from exc


NO_TEMPLATE_YET = (
    "No template is selected for this session yet: select one with "
    "select_template once the collaborator confirmed it."
)
NO_BASE_YET = (
    "There is no document yet: no Word template is configured, and no attached "
    "Word file was made the document's base (use_attached_document, when the "
    "collaborator asks for it; they confirm it through the platform's approval "
    "step)."
)


async def current_document(
    docs: Documents,
) -> tuple[Active, list[BatchRecord], DocState] | str:
    """The session's base, its edits and the document they give, or why
    there is no document to work on."""
    if not docs.session_id:
        return "No active session."
    try:
        active = await docs.active()
        if active is None:
            return NO_TEMPLATE_YET if docs.library else NO_BASE_YET
        records = await get_word_template_store().list_batch_records(docs.session_id)
        state = await docs.state(active.base, [r.operations for r in records])
    except Exception as exc:  # noqa: BLE001 - a store or replay failure is a tool result, not a crashed turn
        reraise_run_stop(exc)
        if not isinstance(exc, BaseUnavailable):
            logger.exception(
                "[WORD_TEMPLATE] session=%s document unavailable", docs.session_id
            )
        return UNAVAILABLE
    return active, records, state


@dataclass(frozen=True)
class _Trial:
    """A model batch as it would be stored, and the document it gives."""

    batch: Batch
    docx: bytes


async def try_batch(
    docs: Documents,
    active: Active,
    records: Sequence[BatchRecord],
    state: DocState,
    operations: Sequence[Any],
    *,
    changes_template: bool,
    fixed_outline: bool = False,
) -> _Trial | str:
    """Run a model batch on the current document without storing it: the
    trial, or why it is refused (text for the model). The tool stores a
    trial; the check of a planned edit only reads it. Raises BaseUnavailable
    when the template cannot be read."""
    if not operations:
        return "The batch is empty: send at least one operation."
    ops = [normalized(op) for op in operations]
    if _changed_under_the_model(records, SEEN.get(docs.session_id or "")):
        return _CHANGED_UNDER_THE_MODEL
    shape = await docs.template_shape(active.base)
    if noted := _map_note(ops):
        return (
            f'Not applied: "{noted}" is a note of the document map (colour, '
            "bold, list...), never document text. Write the text alone: its "
            "colour and look come from the template."
        )
    found = await asyncio.to_thread(inspect_set_texts, ops, state.docx)
    if found.renumbered:
        return _renumbered(found.renumbered)
    if found.unchanged:
        # A text already in place changes nothing: dropped, never blocking
        # the rest of the batch; refused only when nothing else is left.
        ops = [
            op
            for op in ops
            if not (
                isinstance(op, Mapping)
                and op.get("op") == "set_text"
                and op.get("address") in found.unchanged
            )
        ]
        if not ops:
            return _unchanged(found.unchanged)
    if found.typed_titles and shape.sub_heading_levels and not fixed_outline:
        mark = "#" * min(shape.sub_heading_levels)
        ops = [
            {"op": "write", "from": op["address"], "markdown": f"{mark} {op['text']}"}
            if isinstance(op, Mapping)
            and op.get("op") == "set_text"
            and op.get("address") in found.typed_titles
            else op
            for op in ops
        ]
    levels = shape.sub_heading_levels

    def as_sub_headings(op: Any) -> Any:
        # Bold and over-deep titles become sub-headings first, still carrying
        # their typed numbers, which then give back the intended hierarchy.
        if not levels:
            return op
        return _titles_by_numbering(
            _bold_titles_as_sub_headings(
                _within_sub_levels(op, max(levels)), min(levels)
            ),
            sorted(levels),
        )

    if fixed_outline and not changes_template:
        # A set outline: a chapter with the template's sub-headings keeps its
        # bold lines as written; any heading line is a sub-chapter the
        # collaborator approves first, never turned bold behind their back.
        locked = await asyncio.to_thread(
            chapters_with_template_sub_headings, state.docx, shape.headings
        )
        ops = [
            op
            if isinstance(op, Mapping)
            and (op.get("from") or op.get("address")) in locked
            else as_sub_headings(op)
            for op in ops
        ]
        if proposed := _heading_titles(ops):
            return _sub_chapters_to_approve(proposed)
    elif fixed_outline or not changes_template:
        ops = [as_sub_headings(op) for op in ops]
    try:
        # Adjusted before it is stored, so a replay rebuilds the same document.
        ops = await asyncio.to_thread(fit_to_document, ops, state.docx)
    except Exception:  # noqa: BLE001 - an odd document: the batch goes as sent
        logger.warning(
            "[WORD_TEMPLATE] session=%s batch not adjusted",
            docs.session_id,
            exc_info=True,
        )
    sub_levels = shape.sub_heading_levels
    if not changes_template and not _heading_levels(ops) <= sub_levels:
        return _new_heading(sub_levels)
    numbered = _numbered_bold_title(ops)
    if numbered is not None:
        return _numbered_title(numbered, sub_levels)
    images = await images_for(docs.session_id or "", [ops])
    try:
        docx = await asyncio.to_thread(
            apply_batch,
            state.docx,
            ops,
            images,
            protected_tables=shape.tables,
            template_headings=shape.headings,
        )
    except BatchError as exc:
        return (
            "Nothing was applied. Fix these problems and send the whole batch "
            "again:\n- " + "\n- ".join(exc.problems)
        )
    except Exception:  # noqa: BLE001 - an engine failure on an odd document must not end the turn
        logger.exception(
            "[WORD_TEMPLATE] session=%s batch failed unexpectedly", docs.session_id
        )
        return (
            "This batch could not be applied (nothing was applied). Split it "
            "into smaller batches, or change the operation that touches the "
            "most complex element."
        )
    # Stored in its canonical form ("from", no defaults).
    batch: Batch = [
        parse_operation(op).model_dump(by_alias=True, exclude_none=True) for op in ops
    ]
    return _Trial(batch, docx)


_DEEP_HEADING_RE = re.compile(r"^(#{1,6})(?=[ \t])", re.MULTILINE)


def _within_sub_levels(op: Any, deepest: int) -> Any:
    """A heading line deeper than the template's deepest sub-heading level
    ("### 1.1 Scope" when it has only "##") is meant as a sub-heading: it
    takes that level instead of being refused."""
    if not (
        isinstance(op, Mapping)
        and op.get("op") in _WRITING_OPS
        and isinstance(op.get("markdown"), str)
    ):
        return op
    markdown = _DEEP_HEADING_RE.sub(
        lambda m: "#" * min(len(m.group(1)), deepest), op["markdown"]
    )
    return {**op, "markdown": markdown}


_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# A whole line in bold, used as a title ("**Context** :").
_BOLD_TITLE_RE = re.compile(r"^[ \t]*\*\*([^*\n]{1,80}?)\*\*[ \t]*:?[ \t]*$")


def _bold_titles_as_sub_headings(op: Any, level: int) -> Any:
    """A bold line, or a line typed with its section number ("3.2 Scope"),
    followed by content is a title: in a template with sub-headings it
    becomes one, so it is styled, numbered and listed in the
    table of contents like the template's own. A bold label ending with a
    colon that introduces a list ("**Goals**:") stays bold."""
    if not (
        isinstance(op, Mapping)
        and op.get("op") in _WRITING_OPS
        and isinstance(op.get("markdown"), str)
    ):
        return op
    lines = op["markdown"].split("\n")

    def after(i: int) -> str | None:
        return next((rest for rest in lines[i + 1 :] if rest.strip()), None)

    # Lines written alike are siblings: colon-ended bold lines are labels
    # only when every one of them introduces a list.
    colon_lines = [
        i
        for i, line in enumerate(lines)
        if _BOLD_TITLE_RE.match(line) and line.rstrip().endswith(":")
    ]
    labels = all(_LIST_LINE_RE.match(after(i) or "") for i in colon_lines)
    for i, line in enumerate(lines):
        match = _BOLD_TITLE_RE.match(line)
        title = (
            match.group(1)
            if match is not None
            else line
            if TYPED_TITLE_RE.match(line)
            else None
        )
        following = after(i)
        if title is None or following is None or _BOLD_TITLE_RE.match(following):
            continue
        if labels and i in colon_lines:
            continue
        lines[i] = f"{'#' * level} {title.strip().rstrip(':').strip()}"
    return {**op, "markdown": "\n".join(lines)}


_HASHES_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+")


def _map_note(operations: Sequence[Any]) -> str | None:
    """A map note ("{blue}") copied into the text a batch writes."""
    for op in operations:
        if not isinstance(op, Mapping):
            continue
        for key in ("text", "markdown", "replace"):
            value = op.get(key)
            if isinstance(value, str) and (match := MAP_NOTE_RE.search(value)):
                return match.group(0)
    return None


def _heading_titles(operations: Sequence[Any]) -> list[str]:
    """The titles of the heading lines a batch writes."""
    return [
        _HASHES_RE.sub("", line).strip()
        for op in operations
        if isinstance(op, Mapping)
        and op.get("op") in _WRITING_OPS
        and isinstance(op.get("markdown"), str)
        for line in op["markdown"].split("\n")
        if _HASHES_RE.match(line)
    ]


def _sub_chapters_to_approve(titles: Sequence[str]) -> str:
    named = ", ".join(f'"{t}"' for t in titles[:6])
    return (
        f"Not applied: this template's outline is set, so adding the sub-chapters "
        f"{named} needs the collaborator's approval. In your message, tell them the "
        "sub-chapters you will add, then send the same batch again with "
        "changes_template set to true: the platform asks their approval. If they "
        "would rather not, write these titles as **bold** lines."
    )


_NUMBERED_TITLE_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?[ \t]+(.+)$")


def _titles_by_numbering(op: Any, levels: Sequence[int]) -> Any:
    """Title lines numbered at several depths ("2. Phase 1", "2.1 Goals")
    keep that hierarchy: the shallowest depth takes the template's first
    sub-heading level, and so on; a depth the template has no level for
    stays a bold line."""
    if not (
        isinstance(op, Mapping)
        and op.get("op") in _WRITING_OPS
        and isinstance(op.get("markdown"), str)
    ):
        return op
    lines = op["markdown"].split("\n")
    found: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        if not _HASHES_RE.match(line):
            continue
        text = _HASHES_RE.sub("", line).strip().strip("*").strip().rstrip(":").strip()
        if match := _NUMBERED_TITLE_RE.match(text):
            depth = match.group(1).count(".") + 1
            found.append((i, depth, match.group(2).strip("* ").strip()))
    depths = sorted({depth for _i, depth, _title in found})
    if len(depths) < 2:
        return op
    for i, depth, title in found:
        rank = depths.index(depth)
        lines[i] = (
            f"{'#' * levels[rank]} {title}" if rank < len(levels) else f"**{title}**"
        )
    return {**op, "markdown": "\n".join(lines)}


def _heading_levels(operations: Sequence[Any]) -> frozenset[int]:
    """The levels of the Markdown heading lines a batch writes."""
    return frozenset(
        level
        for op in operations
        if isinstance(op, Mapping)
        and op.get("op") in _WRITING_OPS
        and isinstance(op.get("markdown"), str)
        for level in markdown_features(op["markdown"]).heading_levels
    )


# A title typed as a whole bold line with a section number: "**3.2 Costs**".
_NUMBERED_BOLD_RE = re.compile(
    r"^\s*\*\*\s*(\d+(?:\.\d+)+\.?\s+[^*]+?)\s*\*\*\s*:?\s*$"
)


def _numbered_bold_title(operations: Sequence[Any]) -> str | None:
    for op in operations:
        if not isinstance(op, Mapping) or op.get("op") not in (
            *_WRITING_OPS,
            "set_text",
        ):
            continue
        text = op.get("markdown") if op.get("op") != "set_text" else op.get("text")
        for line in str(text or "").splitlines():
            if match := _NUMBERED_BOLD_RE.match(line):
                return match.group(1)
    return None


def _sub_heading_marks(levels: frozenset[int]) -> str:
    return " or ".join(f'"{"#" * level} "' for level in sorted(levels))


def _new_heading(sub_levels: frozenset[int]) -> str:
    inside = (
        f"Inside a chapter, a title is a {_sub_heading_marks(sub_levels)} "
        "sub-heading line (the levels this template uses)."
        if sub_levels
        else "This template has no sub-heading level: a title inside a "
        "chapter is a **bold** line."
    )
    return (
        "Not applied: this batch adds a heading of a level that is not a "
        f"sub-heading of this template. {inside} Add a chapter only when the "
        "collaborator asked for one: then "
        "tell them what you will add and send the batch again with "
        "changes_template set to true, for their approval."
    )


def _unchanged(addresses: Sequence[str]) -> str:
    return (
        f"Not applied: {', '.join(addresses)} already holds this text, so nothing "
        'would change. To turn a line into a sub-heading, set its text to "## '
        'Title"; read the part again to see what it holds.'
    )


def _renumbered(addresses: Sequence[str]) -> str:
    return (
        "Not applied: Word numbers headings by their place, so a typed number "
        f"changes nothing ({', '.join(addresses)}). To give a chapter another "
        'number, move it: {"op": "move", "from": <its heading>, "before" or '
        '"after": <another heading>}, in a batch of its own, only when the '
        "collaborator asked for it (they approve it)."
    )


def _numbered_title(title: str, sub_levels: frozenset[int]) -> str:
    how = (
        f"write it as a sub-heading line ({_sub_heading_marks(sub_levels)}) "
        "without its number: Word numbers it and lists it in the table of "
        "contents"
        if sub_levels
        else "write it without its number: this template has no sub-heading level"
    )
    return f'Not applied: "{title}" is a numbered title typed in bold; {how}.'


_CHANGED_UNDER_THE_MODEL = (
    "Nothing was applied: the collaborator changed the document since you last "
    "read it, so your addresses may be wrong. Read the parts you are editing "
    "again (read_template), start from the collaborator's version, then send "
    "the batch again."
)


def log_mark(batches: Sequence[Batch]) -> str:
    return hashlib.sha256(
        json.dumps(list(batches), sort_keys=True).encode()
    ).hexdigest()


def _changed_under_the_model(records: Sequence[BatchRecord], seen: str | None) -> bool:
    """Whether the document changed since the model last read it (``seen``,
    a log mark from this pod), so its addresses may point at shifted places.
    Without a mark, a collaborator batch after the model's last one."""
    if seen is not None:
        return log_mark([r.operations for r in records]) != seen
    last_collaborator = max(
        (r.seq for r in records if r.author == "collaborator"), default=0
    )
    last_model = max((r.seq for r in records if r.author == "model"), default=0)
    return last_collaborator > last_model


# --- what a batch addresses, what the engine's replies say ----------------------------

EDIT_TOOL = "edit_document"
UNDO_TOOL = "undo_last_edit"
CLEANUP_TOOL = "remove_unused_template_parts"
READ_MARK = "(current state):"
SHIFTED = "Addresses after a structural change have shifted"
# A part shown as it is now: by a read, or by an applied edit's reply.
SHOWN = re.compile(rf"^Part (\S+) (?:{re.escape(READ_MARK)}|now:)", re.MULTILINE)
# A body block (P12, T3), as opposed to a cell, header, footer or text box.
_BODY_BLOCK = re.compile(r"^[PT]\d+$")
_WRITING_OPS = ("write", "insert_after")
PART_NOW = re.compile(r"^Part (\S+) now:", re.MULTILINE)


def written_body_addresses(operations: Any) -> list[str]:
    """The body addresses a batch writes content into (write / insert_after)."""
    out: list[str] = []
    for raw in operations if isinstance(operations, list) else []:
        op = normalized(raw)
        if not isinstance(op, Mapping) or op.get("op") not in _WRITING_OPS:
            continue
        for field in ("address", "from", "to"):
            value = op.get(field)
            if isinstance(value, str) and _BODY_BLOCK.match(value.strip()):
                out.append(value.strip())
    return out


def rewritten_addresses(operations: Any) -> list[tuple[str, str]]:
    """The (first, last) body ranges a batch rewrites whole: write ranges
    and set_text targets. Not included: replace_text (a detail inside a
    sentence), remove (always confirmed by the collaborator), and headers or
    footers (each document updates its identification there)."""
    out: list[tuple[str, str]] = []
    for op in map(normalized, operations if isinstance(operations, list) else []):
        if not isinstance(op, Mapping):
            continue
        target = op.get("address") or op.get("from")
        if isinstance(target, str) and target.strip()[:1] in ("H", "F"):
            continue
        kind = op.get("op")
        if kind == "set_text" and isinstance(op.get("address"), str):
            out.append((op["address"].strip(), op["address"].strip()))
        elif kind == "write" and isinstance(op.get("from"), str):
            first = op["from"].strip()
            last = op.get("to") if isinstance(op.get("to"), str) else first
            out.append((first, str(last).strip()))
    return out


def batch_addresses(operations: Any) -> list[str]:
    """Every address a batch names (address, from, to)."""
    ops = operations if isinstance(operations, list) else []
    return operation_addresses(
        [op for op in map(normalized, ops) if isinstance(op, Mapping)]
    )
