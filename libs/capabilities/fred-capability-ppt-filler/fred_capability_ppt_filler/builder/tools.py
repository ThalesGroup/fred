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

"""Chat-time tools of ``ppt_builder``: ``build_presentation`` and the image
folder listing.

Same seams as the filler's tools: typed context through the closure, image
bytes prefetched on the event loop, the CPU-bound render in one thread under
the package's heavy-job slot, delivery through the workspace port with the
shared PDF preview part.

The model sends content only; :func:`assign.assign` picks the template slide
for each entry. A malformed call never fails validation (the arguments are
coerced), a slide that fits nothing builds nothing and returns a structured
``needs_revision`` error, and every error result carries its text so the user
sees it instead of an opaque failure.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import CapabilityContext, EmptyModel
from fred_sdk.contracts.context import (
    LinkKind,
    LinkPart,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from PIL import Image, UnidentifiedImageError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    create_model,
    field_validator,
)
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder.assign import (
    SHAPE_HINTS,
    Assignment,
    Repeat,
    VarietyCheck,
    assign,
    assignable,
)
from fred_capability_ppt_filler.builder.changes import (
    ChangeError,
    SlideChange,
    apply_changes,
    change_shape,
)
from fred_capability_ppt_filler.builder.checks import SlideReport
from fred_capability_ppt_filler.builder.deck_plans import get_deck_plan_store
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    SlideKind,
    TemplateInventory,
)
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    PlanColumn,
    PlanItem,
    PlanTable,
    SlidePlan,
    field_hints,
    has_content,
    zone_summary,
)
from fred_capability_ppt_filler.builder.render import RenderError, render_deck
from fred_capability_ppt_filler.concurrency import (
    acquire_heavy_job_slot,
    release_heavy_job_slot,
)
from fred_capability_ppt_filler.fill import (
    BuildNote,
    BuiltSlide,
    PptPreviewPart,
    _pdf_key_for,
    _prefetch_image_bytes,
    _preview_version,
    _sanitize_output_file_name,
    cast_ui_part,
)
from fred_capability_ppt_filler.images import NotAnImageError, prepare_picture

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fred_capability_ppt_filler.builder.capability import PptBuilderConfig

logger = logging.getLogger(__name__)

PPT_BUILDER_CAPABILITY_ID = "ppt_builder"
BUILD_TOOL_NAME = "build_presentation"
LIST_IMAGES_TOOL_NAME = "list_images_in_folder"
_TOOL_REF = "ppt_builder_build"
_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
_PDF_CONTENT_TYPE = "application/pdf"
_DEFAULT_FILE_NAME = "presentation.pptx"
_IMAGE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".svg",
)

_BUSY_MESSAGE = (
    "No deck was built: the server is busy building other presentations. Tell the user and "
    "offer to try again in a moment; then make ONE call, never several calls at once."
)


# --- catalogue --------------------------------------------------------------------------


_DUPLICATE = (
    "Ignored: the same build_presentation call is already being built in this answer. "
    "Nothing to do: use that call's result and do not describe this one as a separate deck."
)


def _jsonable(value: Any) -> Any:
    return value.model_dump() if isinstance(value, BaseModel) else str(value)


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    """An error result whose text is Fred-owned, so the runtime shows it."""
    return message, ToolInvocationResult(
        tool_ref=_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def offered_kinds(inventory: TemplateInventory) -> List[SlideKind]:
    kinds = {p.kind for p in assignable(inventory)}
    return [k for k in SLIDE_KINDS if k in kinds]


def catalogue(inventory: TemplateInventory) -> str:
    """One line per kind the template offers, with every distinct variant: its
    label and what it holds. A hidden variant is one the model never writes for."""
    variants: Dict[str, Dict[str, str]] = {}
    for pattern in assignable(inventory):
        variants.setdefault(pattern.kind, {}).setdefault(
            zone_summary(pattern), pattern.label
        )
    return "\n".join(
        f"- {kind}: "
        + " | ".join(f"{label}: {summary}" for summary, label in variants[kind].items())
        for kind in offered_kinds(inventory)
    )


def _args_schema(inventory: TemplateInventory) -> type[BaseModel]:
    """The deck plan, with the kinds this template offers as the `kind` enum
    and each text field's room in its description (JSON schema only:
    validation accepts anything and coerces it)."""
    return _schema_for(
        tuple(offered_kinds(inventory)), field_hints(assignable(inventory))
    )


def _kind_enum(kinds: Tuple[SlideKind, ...]) -> Any:
    """Replace the full `SlideKind` enum the type generates: models read the
    nested `anyOf` and asked for kinds this template does not offer."""

    def extra(schema: Dict[str, Any]) -> None:
        schema.pop("enum", None)
        schema["anyOf"] = [{"type": "string", "enum": list(kinds)}, {"type": "null"}]

    return extra


def _hinted(
    name: str, base: type[BaseModel], hints: Dict[str, str], prefix: str = ""
) -> Dict[str, Any]:
    """`base`'s fields that have a room hint, redeclared with it appended to
    their description (never `maxLength`: the provider would reject the call)."""
    fields: Dict[str, Any] = {}
    for field, info in base.model_fields.items():
        hint = hints.get(prefix + field)
        if hint:
            described = f"{info.description or name + ' ' + field + '.'} {hint}"
            default: Dict[str, Any] = (
                {"default_factory": info.default_factory}
                if info.default_factory
                else {"default": info.default}
            )
            fields[field] = (info.annotation, Field(description=described, **default))
    return fields


# Built per turn otherwise: pydantic model creation costs milliseconds of CPU
# on the event loop; keyed by what the schema shows, so equal templates share it.
@lru_cache(maxsize=64)
def _schema_for(
    kinds: Tuple[SlideKind, ...], hints: Tuple[Tuple[str, str], ...]
) -> type[BaseModel]:
    rooms = dict(hints)
    item = create_model(
        "BuildItem", __base__=PlanItem, **_hinted("Item", PlanItem, rooms, "items.")
    )
    column = create_model(
        "BuildColumn",
        __base__=PlanColumn,
        **_hinted("Column", PlanColumn, rooms, "columns."),
    )
    # Offered only when the template holds a table: the field is noise otherwise.
    table: Any = (
        (Optional[PlanTable], SlidePlan.model_fields["table"])
        if "table" in kinds
        else (SkipJsonSchema[Optional[PlanTable]], None)
    )
    slide_model = create_model(
        "BuildSlide",
        __base__=SlidePlan,
        **_hinted("Slide", SlidePlan, rooms),
        columns=(List[column], Field(default_factory=list)),  # type: ignore[valid-type]
        items=(List[item], Field(default_factory=list)),  # type: ignore[valid-type]
        table=table,
        kind=(
            Optional[SlideKind],
            Field(
                default=None,
                description=(
                    "Optional, after the content: the kind of slide. Left out, the tool "
                    "infers it from the content."
                ),
                json_schema_extra=_kind_enum(kinds),
            ),
        ),
    )
    # Plain objects here: the slide schema repeated under `changes` doubled the
    # tool schema every model call pays for; they are validated as slides below.
    change = create_model(
        "BuildChange",
        __base__=SlideChange,
        slides=(
            List[Dict[str, Any]],
            Field(
                default_factory=list,
                description=(
                    "replace, insert: the new slides, each written as an entry of `slides`, "
                    "with the same fields and rooms: title, subtitle, bullets [...], columns "
                    "[{heading, bullets}], items [{number, heading, text, label, image}], "
                    "image, images, "
                    + ("table {header, rows}, " if "table" in kinds else "")
                    + "notes, kind."
                ),
            ),
        ),
    )
    model = create_model(
        "BuildPresentationArgs",
        __base__=BaseModel,
        __config__=ConfigDict(extra="ignore"),
        __validators__={
            "_lists": field_validator("slides", "changes", mode="before")(_listed)
        },
        slides=(
            List[slide_model],
            Field(
                default_factory=list,
                description="A new deck: every slide, in order. Leave empty when sending `changes`.",
            ),
        ),  # type: ignore[valid-type]
        changes=(
            Optional[List[change]],  # type: ignore[valid-type]
            Field(
                default=None,
                description=(
                    "Instead of `slides`: changes to the last deck of this conversation, "
                    "numbered on its slides; the other slides stay as they are."
                ),
            ),
        ),
        file_name=(
            Optional[str],
            Field(
                default=None,
                description="Short, relevant file name for the deck; '.pptx' is added.",
            ),
        ),
    )
    return model


def _listed(value: Any, info: ValidationInfo) -> Any:
    """`slides: null` beside `changes`, or one change sent as an object: a
    validation error here would reach the user as an opaque tool failure."""
    if value is None:
        return [] if info.field_name == "slides" else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value
    return [value] if isinstance(value, dict) else value


def _to_plan(validated: Any) -> DeckPlan:
    return DeckPlan(
        slides=[
            SlidePlan.model_validate(slide.model_dump()) for slide in validated.slides
        ],
        file_name=validated.file_name,
    )


def _plain_slide(slide: Any) -> Any:
    return slide.model_dump() if isinstance(slide, BaseModel) else slide


def _to_changes(validated: Any) -> List[SlideChange]:
    return [
        change.model_copy(
            update={
                "slides": [
                    SlidePlan.model_validate(_plain_slide(s)) for s in change.slides
                ]
            }
        )
        for change in validated.changes or []
    ]


def _loads(raw: object) -> bool:
    """Whether fetched bytes open as an image (header only: cheap)."""
    if not isinstance(raw, bytes):
        return False
    try:
        with Image.open(io.BytesIO(raw)):
            return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def _assign_loadable(
    inventory: TemplateInventory,
    plan: DeckPlan,
    prefetched: Mapping[str, object],
    variety: VarietyCheck,
    max_uses: int,
) -> Tuple[Assignment, DeckPlan, List[str]]:
    """Assign with the pictures that load only: an id that does not must not
    count as filling a framed picture zone, which would then show its frame."""
    bad = sorted(uid for uid, raw in prefetched.items() if not _loads(raw))
    if bad:
        plan = plan.model_copy(
            update={"slides": [_without(slide, set(bad)) for slide in plan.slides]}
        )
    return assign(inventory, plan, variety, max_uses), plan, bad


def _without(slide: SlidePlan, bad: set[str]) -> SlidePlan:
    items = [
        item.model_copy(update={"image": None}) if item.image in bad else item
        for item in slide.items
    ]
    return slide.model_copy(
        update={
            "image": None if slide.image in bad else slide.image,
            "images": [i for i in slide.images if i not in bad],
            "items": items,
        }
    )


def _summary(
    built: List[BuiltSlide], sent: DeckPlan, bad: List[str], numbers: List[int]
) -> List[BuiltSlide]:
    """The render's per-slide record, with the pictures that did not load
    before the assignment noted on the first part of the slide naming them."""
    unusable = set(bad)
    noted: set[int] = set()
    for slide in built:
        number = numbers[slide.number - 1]
        if not unusable or number in noted:
            continue
        noted.add(number)
        source = sent.slides[number - 1]
        named = [source.image, *source.images, *(i.image for i in source.items)]
        count = len({uid for uid in named if uid in unusable})
        same = next((n for n in slide.notes if n.code == "image_unusable"), None)
        if same is not None:
            same.count = (same.count or 0) + count
        elif count:
            slide.notes.append(BuildNote(code="image_unusable", count=count))
    return built


def _image_ids(plan: DeckPlan) -> set[str]:
    ids: set[str] = set()
    for slide in plan.slides:
        if slide.image:
            ids.add(slide.image)
        ids.update(i for i in slide.images if i)
        ids.update(item.image for item in slide.items if item.image)
    return ids


# Per slide index: (problem, the slide as sent) of the previous needs_revision.
_Previous = Dict[int, Tuple[str, str]]


def _needs_revision(
    assignment: Assignment,
    plan: DeckPlan,
    previous: _Previous,
    repeats: List[Repeat],
    lead: List[str],
    from_changes: bool = False,
) -> tuple[str, ToolInvocationResult]:
    """The problems, each flagged when the previous call already had it, so the
    model never reads the same message twice without learning what changed;
    a first call's variety ask joins them, so it never costs a round of its own."""
    current: _Previous = {}
    slides = []
    # A slide renumbered by `changes` is still the one refused before.
    by_sent = {sent: (problem, sent) for problem, sent in previous.values()}
    for problem in assignment.problems:
        sent = plan.slides[problem.index - 1].model_dump_json()
        entry = problem.as_dict()
        before = previous.get(problem.index) or by_sent.get(sent)
        if before is not None and before[0] == problem.problem:
            entry["repeated"] = (
                "you resent this slide unchanged: apply one of the options"
                if before[1] == sent
                else "the slide changed but this problem is still there: apply one of the options"
            )
        current[problem.index] = (problem.problem, sent)
        slides.append(entry)
    previous.clear()
    previous.update(current)
    payload: Dict[str, Any] = {"status": "needs_revision", "slides": slides}
    text = " ".join(
        lead
        + [
            "No deck was built: some slides cannot be built as sent (see each `problem`). Fix "
            "each slide listed under `slides` with one of its options."
        ]
    )
    if repeats:
        payload["variety"] = _variety(repeats)
        text += " Also, several slides would look the same: " + _VARIETY_ASK.format(
            restated=""
        )
    text += (
        " Then call build_presentation again with the same `changes`, corrected (all of them: "
        "they apply to the deck before them), or the whole deck in `slides`."
        if from_changes
        else " Then call build_presentation again with only `changes` for these slides "
        "(numbers as listed), or the whole deck in `slides`."
    )
    if repeats:
        text += (
            " If the slides under `variety` must stay alike, keep them: the next deck that "
            "fits is built as is."
        )
    return _error(text + "\n" + json.dumps(payload, ensure_ascii=False))


_VARIETY_ASK = (
    "recast some of the slides under `variety` into one of their options (`suggested` names "
    "the kind each slide's content already suits and what that slide holds), rewriting the "
    "content in that shape and to those sizes{restated}."
)


def _variety(repeats: List[Repeat]) -> List[Dict[str, Any]]:
    return [
        {
            "slides": r.slides,
            "kind": r.kind,
            "at_most": r.at_most,
            **({"suggested": r.suggested} if r.suggested else {}),
            "options": [f"another '{r.kind}' variant: {u}" for u in r.unused]
            + r.others,
        }
        for r in repeats
    ]


def _variety_revision(
    repeats: List[Repeat], assignment: Assignment
) -> tuple[str, ToolInvocationResult]:
    """Asked on the first call of a turn, on the first deck of a conversation:
    the repeated slides and what each alternative suits; a resend is built."""
    kinds = [p.kind if p else None for p in assignment.patterns]
    restated = any(
        kinds[i] in ("two_columns", "comparison") and kinds[i + 1] == "table"
        for r in repeats
        for i in (n - 1 for n in r.slides)
        if i + 1 < len(kinds)
    )
    payload = {"status": "needs_revision", "variety": _variety(repeats)}
    return _error(
        "No deck was built yet: several slides would look the same: "
        + _VARIETY_ASK.format(
            restated=", and do not restate a table's content as columns on the slide "
            "before it"
            if restated
            else "",
        )
        + " Then call build_presentation again with `changes` replacing those slides, or the "
        "whole deck in `slides`. If these slides must stay alike, send the same call again: it "
        "will be built as is.\n" + json.dumps(payload, ensure_ascii=False)
    )


# The two success texts below start so; a needs_revision or an error never does.
_DELIVERED = ("Delivered: '", "The presentation '")


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    blocks = content if isinstance(content, list) else []
    return "".join(
        b if isinstance(b, str) else str(b.get("text") or "")
        for b in blocks
        if isinstance(b, (str, dict))
    )


def deck_delivered(history: Sequence[BaseMessage]) -> bool:
    """Whether this conversation already holds a deck: an earlier
    build_presentation result in the messages the model was sent delivered one.
    Matched by its call id: the platform strips message names before the model call."""
    calls = {
        call.get("id")
        for m in history
        if isinstance(m, AIMessage)
        for call in m.tool_calls
        if call.get("name") == BUILD_TOOL_NAME
    }
    return any(
        isinstance(m, ToolMessage)
        and (m.name == BUILD_TOOL_NAME or m.tool_call_id in calls)
        and _text_of(m.content).startswith(_DELIVERED)
        for m in history
    )


def _no_history() -> Sequence[BaseMessage]:
    return ()


def _issue_line(report: SlideReport) -> str:
    parts = []
    if report.truncated:
        parts.append(
            f"text cut to fit in {', '.join(report.truncated)} (shorten it to show it whole)"
        )
    if report.removed:
        removed = ", ".join(f"'{t}'" for t in report.removed)
        parts.append(f"template example text removed: {removed} (nothing to do)")
    if report.lost:
        parts.append(
            f"not placed: {', '.join(report.lost)} (move it to a field this slide shows, "
            "or drop it)"
        )
    parts.extend(f"{s} (nothing to do)" for s in report.shrunk)
    return f"Slide {report.position}: " + "; ".join(parts) + "."


def _build_notes(plan: DeckPlan, issues: List[SlideReport], notes: List[str]) -> str:
    """What the agent should know about the deck it just built."""
    lines = [
        f"Entry {index} of 'slides' was not a slide object and was skipped: if it was "
        "meant as a slide, write it as an object (title, bullets…)."
        for index, slide in enumerate(plan.slides, start=1)
        if slide.invalid_entry is not None
    ]
    lines += [_issue_line(report) for report in issues] + notes
    if not lines:
        return ""
    return (
        "\nTo review (if it matters, call again with `changes` for those slides; the new build "
        "replaces this one):\n" + "\n".join(lines)
    )


def _prepare_and_render(
    template_bytes: bytes,
    inventory: TemplateInventory,
    plan: DeckPlan,
    patterns: List[Any],
    prefetched: Dict[str, object],
    numbers: Optional[List[int]] = None,
):
    """Picture validation/transcoding and the render, together in one worker
    thread: Pillow decoding a large WEBP is hundreds of milliseconds of CPU.
    An unusable picture is left out (the renderer reports it), never fatal."""
    images = {}
    for document_id, raw in prefetched.items():
        if isinstance(raw, Exception):
            continue
        try:
            images[document_id] = prepare_picture(raw)  # type: ignore[arg-type]
        except NotAnImageError:
            continue
    return render_deck(template_bytes, inventory, plan, patterns, images, numbers)


# --- the base of a `changes` call ----------------------------------------------------------

_BOTH_MODES = (
    "No deck was built: the call sent both `slides` and `changes`. Send `slides` alone for a "
    "new deck, or `changes` alone to change the last deck."
)
_NO_CHANGE = (
    "No deck was built: `changes` is empty. List at least one change, or send the whole deck "
    "in `slides`."
)
_NO_BASE = (
    "No deck was built: there is no previous deck in this conversation to change. Send the "
    "whole deck in `slides`."
)
_BASE_UNREADABLE = (
    "No deck was built: the previous deck could not be read right now. Send the whole deck "
    "in `slides`."
)


class _BasePlans:
    """The last evaluated plan of this conversation and agent, in the shared
    store; without a session (eval, tests) there is nothing to share."""

    def __init__(self, session_id: Optional[str], instance_id: Optional[str]) -> None:
        self._key = (session_id, instance_id or "") if session_id else None
        self._written: Optional[str] = None

    async def read(self) -> Optional[DeckPlan]:
        if self._key is None:
            return None
        stored = await get_deck_plan_store().get(*self._key)
        if stored is None:
            return None
        try:
            return DeckPlan.model_validate_json(stored)
        except ValueError:
            logger.warning("[PPTBUILD][TOOL] stored base plan no longer validates")
            return None

    async def write(self, plan: DeckPlan) -> None:
        if self._key is None:
            return
        data = plan.model_dump_json()
        if data == self._written:
            return
        try:
            await get_deck_plan_store().put(*self._key, data)
            self._written = data
        except Exception:  # noqa: BLE001 - the deck itself is unaffected
            logger.warning("[PPTBUILD][TOOL] base plan not stored", exc_info=True)


# --- tools ------------------------------------------------------------------------------------


def build_list_images_tool(
    ctx: "CapabilityContext[PptBuilderConfig, EmptyModel]",
) -> BaseTool:
    """List the image documents of one team folder, resolved at call time."""
    services = ctx.services

    async def _list_images(folder: str) -> str:
        port = services.document_folders
        if port is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.document_folders is not available on this execution path."
            )
        normalized = folder.strip().strip("/")
        tag_id = await port.resolve_folder(normalized)
        if tag_id is None:
            return f"No folder named '{normalized}' in the team's resources. Ask the user for the folder path, or use list_document_tree to browse."
        entries = await port.list_folder_documents(tag_id)
        images = [
            e for e in entries if e.document_name.lower().endswith(_IMAGE_SUFFIXES)
        ]
        if not images:
            return (
                f"The folder '{normalized}' holds no image. Build the deck without images, "
                "or ask the user for another folder."
            )
        return json.dumps(
            [{"document_id": e.document_uid, "name": e.document_name} for e in images]
        )

    return StructuredTool.from_function(
        coroutine=_list_images,
        name=LIST_IMAGES_TOOL_NAME,
        description=(
            "List the image documents in one folder of the team's resources (pass the folder path, "
            "e.g. 'Images/Sites'). Returns a JSON list of {document_id, name}; pass a document_id as an "
            "image value in build_presentation. Only needed when the plan uses images."
        ),
    )


_GUIDE_KINDS = ("figures", "timeline", "cards", "process", "table")


def _guide(kinds: List[SlideKind], variety: VarietyCheck, max_uses: int) -> str:
    """Which content suits which offered kind, and the author's max."""
    pairs = [f"{SHAPE_HINTS[k]} → {k}" for k in _GUIDE_KINDS if k in kinds]
    if "table" in kinds:
        pairs[-1] += ", not restated as columns before it"
    lead = (
        f" Shape the content, within the fields and items max each variant lists below: "
        f"{'; '.join(pairs)}."
        if pairs
        else ""
    )
    if variety == "off":
        return lead
    if max_uses == 1:
        return lead + " Each slide of the deck must look different."
    if variety == "kind":
        return lead + (
            f" Use any kind below on at most {max_uses} slides per deck, cover, agenda, "
            "section and closing aside."
        )
    return lead + f" Use any variant below at most {max_uses} times per deck."


def _description(
    inventory: TemplateInventory, variety: VarietyCheck, max_uses: int
) -> str:
    kinds = offered_kinds(inventory)
    rules = ""
    if "cover" in kinds:
        rules += " The first slide is always the template's cover."
    if "closing" in kinds:
        rules += " A closing slide can only be the last one."
    return (
        "Build a PowerPoint presentation from a plan of slides, on the agent's template. "
        "A NEW deck: write out every slide in `slides`, in order, in ONE call - an eight-slide deck means "
        "eight entries, and the deck holds exactly what you send, not what you planned. Never split a deck "
        "across several calls and never call this tool twice at once. "
        "To CHANGE the last deck of this conversation (a fix after needs_revision, or a change the user asks "
        'for), send only `changes`, numbered on that deck\'s slides: {"op": "replace", "slide": N, "slides": '
        '[...]}, {"op": "insert", "after": N (0 = at the start), "slides": [...]}, {"op": "remove", "slide": '
        'N}, {"op": "edit", "slide": N, "field": "title" | "bullets[1]" | "items[2].label" (indexes from 0), '
        '"value": ...}. The other slides stay exactly as they were and the whole deck is rebuilt. '
        "To change text inside a slide, use `edit`: the slide keeps its design; `replace` is for "
        "a different slide (one of the same kind keeps the replaced slide's design when it fits). "
        'When the user wants a slide to look like another ("same layout/design as slide M"), send '
        '{"op": "edit", "slide": N, "field": "like", "value": M}: slide N takes slide M\'s template slide; '
        "editing `kind` or resending the same text never changes a design. "
        "For each slide write its content: title, subtitle, bullets (telegraphic, "
        "'- ' prefix for a sub-bullet, **bold** allowed), columns [{heading, bullets}], items [{number, "
        "heading, text, label, image}], image/images (document_ids from list_images_in_folder), "
        + ("table {header, rows} for tabular data, " if "table" in kinds else "")
        + "notes; then, "
        "optionally, its `kind` from the list below (left out, it is inferred from the content; a kind "
        "the template cannot use there is replaced by a close kind that holds the content, never an "
        "unrelated one). The tool picks the "
        "template slide for each entry."
        + rules
        + " A slide holds only the fields its kind lists below (no subtitle on a kind that lists "
        "none, item numbers only where listed). Respect the limits below: a slide is not "
        "a document. If a slide fits no slide of the template, nothing is built and the result lists, per "
        "slide, what to change: apply it with `changes`. The result is shown to the user automatically; "
        "never write a download link. Each call's deck replaces the previous one.\n"
        + _guide(kinds, variety, max_uses)
        + "\n"
        "Slide kinds of this template, with each variant's name and what each zone holds at full "
        "size (words, then ≈chars per line × lines; items max N; variants separated by |). Write to "
        "these sizes, counting words:\n" + catalogue(inventory)
    )


def build_builder_tools(
    ctx: "CapabilityContext[PptBuilderConfig, EmptyModel]",
    template_bytes_loader,
    inventory: TemplateInventory,
    history: Callable[[], Sequence[BaseMessage]] = _no_history,
) -> list[BaseTool]:
    """The build tool bound to one turn's context and effective inventory.

    ``template_bytes_loader`` is an async callable returning the template
    bytes (the stored asset, or the built-in template); ``history`` returns the
    messages of the model call that asked for the tool.
    """
    services = ctx.services
    identity = ctx.identity
    args_schema = _args_schema(inventory)
    previous_problems: _Previous = {}
    # Variety is asked on the first call of the turn (one tool instance) only.
    called = False
    variety = ctx.config.variety_check
    max_uses = ctx.config.variety_max_uses

    # Models sometimes send the same call twice in parallel: one build at a time,
    # and a copy of a call still running is answered without a second build.
    build_lock = asyncio.Lock()
    in_flight: set[str] = set()
    # The last plan this turn evaluated and, when `changes` produced it, the plan
    # they applied to and their shape: a corrected resend applies there again.
    turn_base: List[DeckPlan] = []
    turn_parent: List[DeckPlan] = []
    turn_shape: List[Any] = [None]
    plans = _BasePlans(identity.session_id, identity.agent_instance_id)

    async def _build(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        key = json.dumps(kwargs, sort_keys=True, default=_jsonable)
        if key in in_flight:
            return _DUPLICATE, ToolInvocationResult(
                tool_ref=_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=_DUPLICATE),),
            )
        in_flight.add(key)
        try:
            async with build_lock:
                return await _build_plan(**kwargs)
        finally:
            in_flight.discard(key)

    async def _build_plan(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        nonlocal called
        first, called = not called, True
        try:
            validated: Any = args_schema(**kwargs)
            plan = _to_plan(validated)
            changes = None if validated.changes is None else _to_changes(validated)
        except Exception as exc:  # noqa: BLE001 - coercion makes this unexpected
            logger.warning("[PPTBUILD][TOOL] unreadable plan: %s", exc)
            return _error(
                "No deck was built: the slide plan could not be read. Call build_presentation "
                "again with 'slides' as a list of objects, each with its content (title, "
                "bullets, items…)."
            )
        shape: Any = None
        base: Optional[DeckPlan] = None
        if changes is not None and (changes or not plan.slides):
            if plan.slides:
                return _error(_BOTH_MODES)
            if not changes:
                return _error(_NO_CHANGE)
            shape = change_shape(changes)
            try:
                base = turn_base[0] if turn_base else await plans.read()
            except Exception:  # noqa: BLE001 - the model can resend the whole deck
                logger.warning("[PPTBUILD][TOOL] base plan unreadable", exc_info=True)
                return _error(_BASE_UNREADABLE)
            if base is None:
                return _error(_NO_BASE)
            # Models resend refused changes corrected, never applied twice.
            if turn_parent and shape == turn_shape[0]:
                base = turn_parent[0]
            try:
                changed = apply_changes(base, changes)
            except ChangeError as exc:
                return _error(
                    "No deck was built: some changes cannot be applied to the previous "
                    "deck (nothing was changed). Fix them and call again:\n"
                    + "\n".join(exc.problems)
                )
            plan = changed.model_copy(
                update={"file_name": validated.file_name or changed.file_name}
            )

        async def evaluated(stored: DeckPlan) -> None:
            turn_base[:] = [stored]
            turn_parent[:] = [] if base is None else [base]
            turn_shape[0] = shape
            await plans.write(stored)

        if not any(has_content(s) for s in plan.slides if s.invalid_entry is None):
            return _error(
                "No deck was built: every slide of the plan is empty. Write each slide's "
                "content (title, bullets, items…) and call build_presentation again."
            )
        image_ids = _image_ids(plan)
        if image_ids and services.document_content is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.document_content is not available on this execution path."
            )
        # Pictures before the assignment, the template only after it: a plan
        # that needs revision costs no template fetch.
        prefetched = (
            await _prefetch_image_bytes(image_ids, services) if image_ids else {}
        )
        sent = plan
        assignment, plan, bad = await asyncio.to_thread(
            _assign_loadable, inventory, plan, prefetched, variety, max_uses
        )
        unloadable = [
            f"image '{uid}' is not a usable image document and was left out: use a "
            "document_id from list_images_in_folder."
            for uid in bad
        ]
        workspace = services.workspace_fs
        session_id = identity.session_id
        asking = first and variety != "off"
        repeats = [r for r in assignment.repeats if r.revisable] if asking else []
        # Read only when an ask would follow: the usual call adds no work.
        if repeats and deck_delivered(history()):
            repeats = []
        if assignment.problems:
            await evaluated(plan)
            return _needs_revision(
                assignment,
                plan,
                previous_problems,
                repeats,
                unloadable,
                base is not None,
            )
        previous_problems.clear()
        if repeats:
            await evaluated(plan)
            return _variety_revision(repeats, assignment)

        if workspace is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.workspace_fs is not available on this execution path."
            )
        started = time.monotonic()
        try:
            template_bytes = await template_bytes_loader()
        except Exception:  # noqa: BLE001 - surfaced to the agent
            logger.exception("[PPTBUILD][TOOL] template load FAILED")
            return _error(
                "No deck was built: the presentation template could not be loaded right now. "
                "Tell the user and suggest trying again in a moment."
            )

        if not acquire_heavy_job_slot():
            return _error(_BUSY_MESSAGE)
        # Stored as delivered: a split list's parts become slides of their own,
        # so the file, the model and later `changes` share one numbering.
        deck, patterns, numbers = assignment.deck(plan)
        deck = deck.model_copy(
            update={
                "slides": [
                    s.model_copy(
                        update={
                            "built_on": p.id if p else None,
                            "asked_design": None,
                            "asked_from": None,
                        }
                    )
                    for s, p in zip(deck.slides, patterns)
                ]
            }
        )
        try:
            result = await asyncio.to_thread(
                _prepare_and_render,
                template_bytes,
                inventory,
                deck,
                patterns,
                prefetched,
                numbers,
            )
        except RenderError as exc:
            return _error(f"No deck was built: {exc}")
        except Exception:  # noqa: BLE001 - wrapped uniformly for the agent
            elapsed = time.monotonic() - started
            logger.exception("[PPTBUILD][TOOL] render FAILED after %.0fs", elapsed)
            return _error(
                "No deck was built because of an internal problem. Tell the user and suggest "
                "trying again; if it persists, simplify the plan."
            )
        finally:
            release_heavy_job_slot()

        file_name = (
            _sanitize_output_file_name(plan.file_name)
            if plan.file_name
            else _DEFAULT_FILE_NAME
        )
        # Keyed by the deck's name: a deck split over several calls, or retried
        # after a busy answer, is one presentation, not a card per fragment.
        output_path = (
            f"outputs/{session_id}/{file_name}"
            if session_id
            else f"outputs/{file_name}"
        )
        try:
            pptx_artifact = await workspace.write(
                output_path,
                result.pptx,
                content_type=_PPTX_CONTENT_TYPE,
                title=file_name,
            )
        except Exception:  # noqa: BLE001 - surfaced to the agent
            logger.exception("[PPTBUILD][TOOL] upload FAILED")
            return _error(
                "The deck was built but could not be saved to the conversation files, so the "
                "user cannot get it. Tell the user and suggest trying again in a moment."
            )
        await evaluated(deck)

        if result.warnings:
            logger.info("[PPTBUILD][TOOL] render warnings: %s", result.warnings)
        notes = _build_notes(
            plan,
            result.report.issues(),
            result.report.notes + unloadable + assignment.notes,
        )

        pdf_bytes = await convert_office_bytes_to_pdf(
            result.preview_pptx or result.pptx, suffix=".pptx"
        )
        pdf_url: Optional[str] = None
        if pdf_bytes is not None:
            try:
                pdf_artifact = await workspace.write(
                    _pdf_key_for(output_path),
                    pdf_bytes,
                    content_type=_PDF_CONTENT_TYPE,
                    title=_pdf_key_for(file_name),
                )
                pdf_url = pdf_artifact.href
            except Exception as exc:  # noqa: BLE001 - preview is best effort
                logger.warning(
                    "[PPTBUILD][TOOL] preview upload failed (deck still returned): %s",
                    exc,
                )

        if pdf_url and pdf_bytes is not None:
            part = PptPreviewPart(
                preview_id=pptx_artifact.key,
                title=file_name,
                pdf_download_url=pdf_url,
                version=_preview_version(pdf_bytes),
                pptx_download_url=pptx_artifact.href,
                # The stored key is unique per deck; the user downloads the name
                # the model chose.
                file_name=file_name,
                capability_id=PPT_BUILDER_CAPABILITY_ID,
                summary=_summary(result.report.built, sent, bad, numbers),
            )
            return (
                f"Delivered: '{file_name}', {result.slide_count} slides. This replaces any deck built earlier "
                "in this answer. A preview opens beside the chat and a download button is shown "
                "automatically; do not write a download link. To change it, send only `changes` numbered "
                f"on the file's slides (1 to {result.slide_count}, a list continued on two slides counts "
                "two); every call rebuilds the whole deck. Describe to the user only the slides the deck "
                "actually holds." + notes,
                ToolInvocationResult(
                    tool_ref=_TOOL_REF, ui_parts=(cast_ui_part(part),)
                ),
            )
        link = LinkPart(
            href=pptx_artifact.href,
            title=f"Download {pptx_artifact.file_name}",
            kind=LinkKind.download,
            mime=_PPTX_CONTENT_TYPE,
            document_uid=pptx_artifact.document_uid,
            file_name=pptx_artifact.file_name,
        )
        return (
            f"The presentation '{file_name}' ({result.slide_count} slides) is ready (no preview could be "
            "generated, only the download). A download button is shown automatically; do not write a link. "
            f"To change it, send only `changes` numbered on the file's slides (1 to {result.slide_count})."
            + notes,
            ToolInvocationResult(tool_ref=_TOOL_REF, ui_parts=(cast_ui_part(link),)),
        )

    description = _description(inventory, variety, max_uses)
    build_tool = StructuredTool.from_function(
        coroutine=_build,
        name=BUILD_TOOL_NAME,
        description=description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )
    return [build_tool, build_list_images_tool(ctx)]
