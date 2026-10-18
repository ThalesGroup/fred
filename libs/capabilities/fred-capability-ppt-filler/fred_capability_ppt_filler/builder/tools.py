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
``needs_revision`` result (not an error: the model revises and calls again),
and every error result carries its text so the user sees it instead of an
opaque failure.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from collections import Counter
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
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    create_model,
    field_validator,
)
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder import story
from fred_capability_ppt_filler.builder.assign import (
    SECTION_RULE,
    SHAPE_HINTS,
    Assignment,
    Repeat,
    SlideProblem,
    VarietyCheck,
    assign,
    assignable,
    unplaced,
)
from fred_capability_ppt_filler.builder.changes import (
    CLEARABLE,
    ChangeError,
    Origin,
    SlideChange,
    apply_changes,
    deck_delta,
    repinned,
    unchanged,
)
from fred_capability_ppt_filler.builder.checks import SlideReport
from fred_capability_ppt_filler.builder.deck_plans import get_deck_plan_store
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    SlideKind,
    TemplateInventory,
)
from fred_capability_ppt_filler.builder.plan import (
    REPEAT_LAYOUT_HINT,
    DeckPlan,
    PlanChart,
    PlanColumn,
    PlanItem,
    PlanTable,
    SlidePlan,
    Trend,
    as_flag,
    field_hints,
    has_content,
    without_hidden,
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
from fred_capability_ppt_filler.pptx_archive import slide_fingerprints

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


def _parallel(first: Mapping[str, Any], count: int, position: int) -> str:
    slides = first.get("slides")
    head = slides[0] if isinstance(slides, list) and slides else None
    title = head.get("title") if isinstance(head, dict) else None
    which = f" (the one whose first slide is '{title}')" if title else ""
    return (
        f"No deck was built: build_presentation was called {count} times at once in this "
        f"answer; only the first call{which} is processed and this one (call {position} of "
        f"{count}) was ignored. A deck is never split across calls: send ONE call with every "
        "slide in `slides`, the cover first. To add or change slides of a delivered deck, send "
        'only `changes` ({"op": "insert", "after": N, "slides": [...]}, {"op": "replace", '
        '"slide": N, "slides": [...]}, {"op": "edit", ...}). Read the first call\'s result '
        "before calling again, and do not describe this call to the user as a deck."
    )


def round_refusal(
    messages: Sequence[BaseMessage], call_id: Optional[str]
) -> Optional[str]:
    """The refusal for a build call that is not the first of its model round:
    calls sent together are fragments or copies of one deck, so the first in
    the assistant message's order is the one built, whatever finishes first."""
    if not call_id:
        return None
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        builds = [c for c in message.tool_calls if c.get("name") == BUILD_TOOL_NAME]
        ids = [c.get("id") for c in builds]
        if call_id in ids:
            position = ids.index(call_id) + 1
            if position == 1:
                return None
            return _parallel(builds[0].get("args") or {}, len(builds), position)
    return None


def _already_delivered(file_name: str, slide_count: int) -> str:
    return (
        f"No deck was built: unchanged, deck already delivered as '{file_name}' "
        f"({slide_count} slides). This plan is exactly that deck, so nothing was rebuilt and "
        "the user's file is the same. Do not tell the user it was changed or rebuilt; to "
        "change it, send only `changes`."
    )


# Ends every revision: models planned the fix, then ended the turn without the call.
_NEXT_CALL = (
    " Your very next message MUST be a new build_presentation call with these fixes applied, "
    "never a final answer, unless the user must decide something first. Make it as a real tool call: "
    "never write the call, its JSON or the planned fixes in your reply text."
)


def _same_call(problems: str, from_changes: bool) -> str:
    """A call identical to one refused this turn gets the same answer: say so,
    and offer what breaks the loop rather than evaluate it again."""
    other = (
        "drop the change that causes it, resending every other change: this one changed nothing"
        if from_changes
        else "leave that slide out"
    )
    return (
        "No deck was built: this call is identical to one already refused in this answer, so "
        f"it is refused again ({problems}). Do not resend it: apply one of the options given "
        'then, or send each listed slide whole with {"op": "replace", "slide": N, "slides": '
        f"[...]}} in `changes` (numbers as listed), or {other}." + _NEXT_CALL
    )


def _jsonable(value: Any) -> Any:
    return value.model_dump() if isinstance(value, BaseModel) else str(value)


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    """A failure (bad call, storage, render): Fred-owned text, so the runtime shows it."""
    return message, ToolInvocationResult(
        tool_ref=_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _answer(message: str) -> tuple[str, ToolInvocationResult]:
    """An expected outcome that built nothing (a revision, nothing to rebuild):
    never an error, or the runtime would end the turn on its text."""
    return message, ToolInvocationResult(
        tool_ref=_TOOL_REF,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def offered_kinds(inventory: TemplateInventory) -> List[SlideKind]:
    kinds = {p.kind for p in assignable(inventory)}
    return [k for k in SLIDE_KINDS if k in kinds]


def chart_hosts(inventory: TemplateInventory) -> str:
    """Where a chart can go: ``chart`` slides, else content areas, else nowhere."""
    zones = [z for p in assignable(inventory) for z in p.zones]
    if any(z.role == "chart" for z in zones):
        return "chart"
    return "content" if any(z.chart_capable for z in zones) else ""


def multi_chart(inventory: TemplateInventory) -> bool:
    """Whether a template slide holds several charts (`charts` is offered)."""
    return any(
        sum(z.role == "chart" for z in p.zones) > 1 for p in assignable(inventory)
    )


def trend_figures(inventory: TemplateInventory) -> bool:
    """Whether items show a figure an arrow can lead (`trend` is offered)."""
    return any(
        "number" in g.item_zones for p in assignable(inventory) for g in p.groups
    )


def takeaway_zones(inventory: TemplateInventory) -> bool:
    """Whether a slide can show its takeaway (`show_takeaways` is offered)."""
    return any(z.takeaway for p in assignable(inventory) for z in p.zones)


def catalogue(inventory: TemplateInventory) -> str:
    """One line per kind the template offers, with every distinct variant: its
    label and what it holds. A hidden variant is one the model never writes for."""
    variants: Dict[str, Dict[str, str]] = {}
    in_content = chart_hosts(inventory) == "content"
    for pattern in assignable(inventory):
        summary = zone_summary(pattern)
        if in_content and any(z.chart_capable for z in pattern.zones):
            # No chart slide: say which content area takes one instead of bullets.
            summary += "; or a chart in place of the bullets"
        variants.setdefault(pattern.kind, {}).setdefault(summary, pattern.label)
    return "\n".join(
        f"- {kind}: "
        + " | ".join(f"{label}: {summary}" for summary, label in variants[kind].items())
        for kind in offered_kinds(inventory)
    )


def _args_schema(
    inventory: TemplateInventory, plan_gate: bool = False
) -> type[BaseModel]:
    """The deck plan, with the kinds this template offers as the `kind` enum
    and each text field's room in its description (JSON schema only:
    validation accepts anything and coerces it); `skip_plan` only with the gate."""
    return _schema_for(
        tuple(offered_kinds(inventory)),
        field_hints(assignable(inventory)),
        bool(chart_hosts(inventory)),
        multi_chart(inventory),
        trend_figures(inventory),
        takeaway_zones(inventory),
        plan_gate,
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
    kinds: Tuple[SlideKind, ...],
    hints: Tuple[Tuple[str, str], ...],
    charts: bool = False,
    several: bool = False,
    trends: bool = False,
    takeaways: bool = False,
    plan_gate: bool = False,
) -> type[BaseModel]:
    rooms = dict(hints)
    # Offered only where an item shows a figure: the arrow leads it.
    trend: Any = (
        (Optional[Trend], PlanItem.model_fields["trend"])
        if trends
        else (SkipJsonSchema[Optional[Trend]], None)
    )
    item = create_model(
        "BuildItem",
        __base__=PlanItem,
        **_hinted("Item", PlanItem, rooms, "items."),
        trend=trend,
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
    chart: Any = (
        (Optional[PlanChart], SlidePlan.model_fields["chart"])
        if charts
        else (SkipJsonSchema[Optional[PlanChart]], None)
    )
    charts_field: Any = (
        (List[PlanChart], SlidePlan.model_fields["charts"])
        if several
        else (SkipJsonSchema[List[PlanChart]], Field(default_factory=list))
    )
    slide_model = create_model(
        "BuildSlide",
        __base__=SlidePlan,
        **_hinted("Slide", SlidePlan, rooms),
        columns=(List[column], Field(default_factory=list)),  # type: ignore[valid-type]
        items=(List[item], Field(default_factory=list)),  # type: ignore[valid-type]
        table=table,
        chart=chart,
        charts=charts_field,
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
                    "takeaway, source, image, images, "
                    + ("table {header, rows}, " if "table" in kinds else "")
                    + ("chart, " if charts else "")
                    + ("charts, " if several else "")
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
            "_lists": field_validator("slides", "changes", mode="before")(_listed),
            "_show": field_validator("show_takeaways", mode="before")(_flag_or_none),
        },
        slides=(
            List[slide_model],
            Field(
                default_factory=list,
                description=(
                    "A new deck, or a rewrite of most slides: every slide, in order. Leave "
                    "empty when sending `changes`."
                ),
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
        audience=(
            Optional[str],
            Field(default=None, description="Optional: who the deck is for."),
        ),
        main_message=(
            Optional[str],
            Field(
                default=None,
                validation_alias=AliasChoices("main_message", "message"),
                description="Optional: the one idea the whole deck leaves, as a sentence.",
            ),
        ),
        skip_plan=(
            (
                Optional[str],
                Field(
                    default=None,
                    description="Only when the user's latest message explicitly asks to "
                    "build without a plan first: quote their words.",
                ),
            )
            if plan_gate
            else (SkipJsonSchema[Optional[str]], None)
        ),
        show_takeaways=(
            (Optional[bool], Field(default=None, description=_SHOW_TAKEAWAYS))
            if takeaways
            else (SkipJsonSchema[Optional[bool]], None)
        ),
    )
    return model


_SHOW_TAKEAWAYS = (
    "true only when the user explicitly asks to show the key messages (takeaways) on "
    "the slides; otherwise leave it out: they stay in the speaker notes."
)


def _flag_or_none(value: Any) -> Optional[bool]:
    """Left out keeps the delivered deck's choice; any spelling of yes is true."""
    return None if value is None else as_flag(value)


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


def _sent(slide: Any) -> SlidePlan:
    """A slide as the model wrote it: a design pin it sent would bypass the
    fit and variety checks, so the fields only the tool sets are dropped."""
    plain = slide.model_dump() if isinstance(slide, BaseModel) else slide
    sent = without_hidden(SlidePlan.model_validate(plain))
    # The units written beside the values are not dumped: kept from the call
    # itself so the one-measure check sees them.
    chart = getattr(slide, "chart", None)
    if isinstance(chart, PlanChart) and sent.chart is not None:
        sent = sent.model_copy(update={"chart": _with_units(sent.chart, chart)})
    written = getattr(slide, "charts", None) or []
    if sent.charts and len(written) == len(sent.charts):
        update = [_with_units(mine, w) for mine, w in zip(sent.charts, written)]
        sent = sent.model_copy(update={"charts": update})
    return sent


def _with_units(mine: PlanChart, written: Any) -> PlanChart:
    if not isinstance(written, PlanChart):
        return mine
    series = [
        ours.model_copy(
            update={
                "units": theirs.units,
                "points": [
                    p.model_copy(update={"units": w.units})
                    for p, w in zip(ours.points, theirs.points)
                ],
            }
        )
        for ours, theirs in zip(mine.series, written.series)
    ]
    return mine.model_copy(update={"series": series})


def _to_plan(validated: Any) -> DeckPlan:
    return DeckPlan(
        slides=[_sent(slide) for slide in validated.slides],
        file_name=validated.file_name,
        audience=validated.audience,
        main_message=validated.main_message,
        show_takeaways=bool(getattr(validated, "show_takeaways", None)),
    )


def _shown_takeaways(plan: DeckPlan) -> DeckPlan:
    """Each slide told whether its takeaway may go on the slide."""
    shown = plan.show_takeaways
    slides = [
        s
        if s.takeaway_shown == shown
        else s.model_copy(update={"takeaway_shown": shown})
        for s in plan.slides
    ]
    return plan.model_copy(update={"slides": slides})


def _to_changes(validated: Any) -> List[SlideChange]:
    return [
        change.model_copy(update={"slides": [_sent(s) for s in change.slides]})
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
    built: List[BuiltSlide],
    sent: DeckPlan,
    bad: List[str],
    numbers: List[int],
    repeated: Optional[Dict[int, bool]] = None,
) -> List[BuiltSlide]:
    """The render's per-slide record, with the pictures that did not load
    before the assignment, and a layout kept (or not) as the user asked,
    noted on the first part of the slide concerned."""
    unusable = set(bad)
    noted: set[int] = set()
    for slide in built:
        number = numbers[slide.number - 1]
        if number in noted:
            continue
        noted.add(number)
        kept = (repeated or {}).get(number)
        if kept is not None:
            code = "layout_repeated" if kept else "layout_not_repeated"
            slide.notes.append(BuildNote(code=code))
        if not unusable:
            continue
        source = sent.slides[number - 1]
        named = [source.image, *source.images, *(i.image for i in source.items)]
        count = len({uid for uid in named if uid in unusable})
        same = next((n for n in slide.notes if n.code == "image_unusable"), None)
        if same is not None:
            same.count = (same.count or 0) + count
        elif count:
            slide.notes.append(BuildNote(code="image_unusable", count=count))
    return built


_DESIGN_NAME_CHARS = 28


def _design_names(inventory: TemplateInventory) -> Dict[str, str]:
    """Each template slide's name as the user sees it, numbered when several
    share one shown (cut) label: the model must never read two designs as one."""
    shown = {
        p.id: p.label
        if len(p.label) <= _DESIGN_NAME_CHARS
        else p.label[: _DESIGN_NAME_CHARS - 1].rstrip() + "…"
        for p in inventory.patterns
        if p.included
    }
    seen: Counter = Counter()
    names: Dict[str, str] = {}
    for pid, label in shown.items():
        seen[label] += 1
        names[pid] = label + (f" #{seen[label]}" if seen[label] > 1 else "")
    return names


def _designs_line(inventory: TemplateInventory, patterns: Sequence[Any]) -> str:
    """One line naming each file slide's template slide, so a request like
    "same layout as slide M" is answered with `like`, not by comparing kinds."""
    names = _design_names(inventory)
    listed = " · ".join(
        f"{number} '{names.get(p.id) or p.label}'"
        for number, p in enumerate(patterns, start=1)
        if p is not None
    )
    return (
        f"\nDesigns: {listed}. Slides with different names look different; to give slide N "
        'the design of slide M, send {"op": "edit", "slide": N, "field": "like", "value": M}.'
    )


def _kinds(inventory: TemplateInventory) -> Dict[str, str]:
    return {p.id: p.kind for p in inventory.patterns}


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
_LIST_FIELDS = ("bullets", "columns", "items", "images")


def _drop_op(option: str, number: int) -> str:
    """A "drop X" option for a whole slide field, with the exact `changes` op
    that does it: models never guessed how to clear a field."""
    name = option.removeprefix("drop ")
    if not option.startswith("drop ") or name not in CLEARABLE:
        return option
    value = "[]" if name in _LIST_FIELDS else "null"
    return f'{option}: {{"op": "edit", "slide": {number}, "field": "{name}", "value": {value}}}'


def _cleared_lines(
    cleared: Mapping[int, List[str]],
    plan: DeckPlan,
    numbers: Optional[List[int]] = None,
) -> List[str]:
    """What a kind edit cleared, numbered on the file when it was built."""
    return [
        f"Slide {numbers.index(n) + 1 if numbers else n}: {', '.join(fields)} cleared, "
        f"as kind '{plan.slides[n - 1].kind}' has no place for "
        f"{'them' if len(fields) > 1 else 'it'} beside the rest (to keep "
        "that text, put it in a field this kind shows)."
        for n, fields in sorted(cleared.items())
    ]


def _numbered(index: int, origins: Optional[Mapping[int, Origin]]) -> Any:
    """A refused slide as the corrected call numbers it: on the deck `changes`
    apply to, or the change that sent it."""
    origin = (origins or {}).get(index)
    if origin is None:
        return index
    if origin[0] == "new":
        return f"new, sent in changes[{origin[1]}]: fix it there"
    return origin[1]


def _needs_revision(
    assignment: Assignment,
    plan: DeckPlan,
    previous: _Previous,
    repeats: List[Repeat],
    lead: List[str],
    origins: Optional[Mapping[int, Origin]] = None,
) -> tuple[str, ToolInvocationResult]:
    """The problems, each flagged when the previous call already had it, so the
    model never reads the same message twice without learning what changed;
    a first call's variety ask joins them, so it never costs a round of its own.
    With ``origins`` (a `changes` call), slides are numbered on the deck the
    changes apply to, as the corrected resend is."""
    from_changes = origins is not None
    current: _Previous = {}
    slides = []
    # A slide renumbered by `changes` is still the one refused before.
    by_sent = {sent: (problem, sent) for problem, sent in previous.values()}
    for problem in assignment.problems:
        sent = plan.slides[problem.index - 1].model_dump_json()
        entry = problem.as_dict()
        origin = (origins or {}).get(problem.index)
        if origin is not None:
            entry["slide"] = _numbered(problem.index, origins)
        if origin is not None and origin[0] == "base":
            entry["options"] = [_drop_op(o, origin[1]) for o in problem.options]
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
        "they apply to the deck before them)."
        if from_changes
        else " Then call build_presentation again with only `changes` for these slides "
        "(numbers as listed), or the whole deck in `slides`."
    )
    if repeats:
        text += (
            " If the slides under `variety` must stay alike, keep them: the next deck that "
            "fits is built as is."
        )
    return _answer(text + _NEXT_CALL + "\n" + json.dumps(payload, ensure_ascii=False))


_VARIETY_ASK = (
    "recast some of the slides under `variety` into one of their options (`suggested` names "
    "the kind each slide's content already suits and what that slide holds), rewriting the "
    "content in that shape and to those sizes{restated}. " + SECTION_RULE
)


def _variety(repeats: List[Repeat]) -> List[Dict[str, Any]]:
    return [
        {
            "slides": r.slides,
            "kind": r.kind,
            "at_most": r.at_most,
            **({"in_a_row": True} if r.in_a_row else {}),
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
    return _answer(
        "No deck was built yet: several slides would look the same: "
        + _VARIETY_ASK.format(
            restated=", and do not restate a table's content as columns on the slide "
            "before it"
            if restated
            else "",
        )
        + " Then call build_presentation again with `changes` replacing those slides, or the "
        "whole deck in `slides`. If these slides must stay alike, send the same call again: it "
        "will be built as is."
        + _NEXT_CALL
        + "\n"
        + json.dumps(payload, ensure_ascii=False)
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


# A plan proposal starts so; a delivery, a revision or an error never does.
_PROPOSED = "Plan proposed: nothing was built yet."


def plan_answered(history: Sequence[BaseMessage]) -> bool:
    """Whether a user message follows the last plan the tool proposed."""
    calls = {
        call.get("id")
        for m in history
        if isinstance(m, AIMessage)
        for call in m.tool_calls
        if call.get("name") == BUILD_TOOL_NAME
    }
    proposal_at = -1
    for position, message in enumerate(history):
        if (
            isinstance(message, ToolMessage)
            and (message.name == BUILD_TOOL_NAME or message.tool_call_id in calls)
            and _text_of(message.content).startswith(_PROPOSED)
        ):
            proposal_at = position
    return proposal_at >= 0 and any(
        m.type == "human" for m in history[proposal_at + 1 :]
    )


def _merged(
    first: List[SlideProblem], second: List[SlideProblem]
) -> List[SlideProblem]:
    """One problem per slide: a slide is revised once, whatever found it."""
    by_index: Dict[int, SlideProblem] = {}
    for problem in first + second:
        same = by_index.get(problem.index)
        if same is None:
            by_index[problem.index] = problem
        else:
            same.problem += "; " + problem.problem
            same.options = list(dict.fromkeys(same.options + problem.options))
    return [by_index[i] for i in sorted(by_index)]


def _evaluate(
    inventory: TemplateInventory,
    plan: DeckPlan,
    prefetched: Mapping[str, object],
    variety: VarietyCheck,
    max_uses: int,
    checked: Sequence[int],
) -> Tuple[Assignment, DeckPlan, List[str]]:
    """The chart-unit check, then the assignment: one revision for both."""
    told = story.check(plan, checked)
    assignment, plan, bad = _assign_loadable(
        inventory, plan, prefetched, variety, max_uses
    )
    assignment.problems = _merged(assignment.problems, told)
    return assignment, plan, bad


def _proposal(
    plan: DeckPlan, assignment: Assignment
) -> tuple[str, ToolInvocationResult]:
    kinds = [p.kind if p else None for p in assignment.patterns]
    payload = {"status": "plan_proposed", "slides": len(plan.slides)}
    return _answer(
        f"{_PROPOSED} Show this outline to the user in their language and ask them to "
        "validate or correct it; end your answer; do not call build_presentation again in "
        "this answer. Once they answer, build it: the whole deck in `slides`, or `changes` "
        f"to this plan.\n{story.outline(plan, kinds)}\n"
        + json.dumps(payload, ensure_ascii=False)
    )


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
    starts: Optional[List[int]] = None,
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
    result = render_deck(
        template_bytes, inventory, plan, patterns, images, numbers, starts
    )
    result.fingerprints = slide_fingerprints(result.pptx)
    return result


# --- the base of a `changes` call ----------------------------------------------------------

# Both sent: which one to keep, by whether the user already has a deck.
_BOTH_MODES = (
    "No deck was built: the call sent both `slides` and `changes`, which never go together. ",
    "There is no delivered deck yet: send only `slides`, with every slide of the deck in "
    "order (the slides `changes` added included).",
    "The user has a deck: send only `changes`, numbered on its slides (`slides` only to "
    "rewrite most of the deck).",
)
_NO_CHANGE = (
    "No deck was built: `changes` is empty. List at least one change, or send the whole deck "
    "in `slides`."
)
_UNCHANGED = (
    "No deck was built: nothing changed. These changes leave the deck as it is (each "
    "value sent equals the current one and every slide keeps its template slide), so the "
    "user's file is the same as before. Do not tell the user it was changed. To change text, "
    'send `edit` with the new text; for the design of another slide ("same layout as slide '
    'M"), send {"op": "edit", "slide": N, "field": "like", "value": M}; resending the kind a '
    "slide already has never moves it to another design. If the deck already shows what the user asked, "
    "tell them so."
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
    """The last delivered deck of this conversation and agent, in the shared
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


def _guide(
    kinds: List[SlideKind],
    variety: VarietyCheck,
    max_uses: int,
    charts: str = "",
    several: bool = False,
) -> str:
    """Which content suits which offered kind, and the author's max."""
    pairs = [f"{SHAPE_HINTS[k]} → {k}" for k in _GUIDE_KINDS if k in kinds]
    if "table" in kinds:
        pairs[-1] += ", not restated as columns before it"
    if charts:
        pairs.append("numbers that compare across categories or over time → chart")
        pairs.append("two measures per item → chart scatter (bubble for a third)")
        pairs.append("items scored on several criteria → chart radar")
    if several:
        pairs.append(
            "two to four related measures side by side, one per chart → a slide with "
            "`charts` (only the counts the catalogue lists)"
        )
    lead = (
        f" Shape the content, within the fields and items max each variant lists below: "
        f"{'; '.join(pairs)}."
        if pairs
        else ""
    )
    if variety == "off":
        return lead
    if max_uses == 1:
        return lead + f" Each slide must look different. {SECTION_RULE}"
    if variety == "kind":
        return lead + (
            f" Use any kind below on at most {max_uses} slides, cover, agenda, "
            f"section and closing aside. {SECTION_RULE}"
        )
    return lead + f" Use any variant below at most {max_uses} times. {SECTION_RULE}"


def _description(
    inventory: TemplateInventory, variety: VarietyCheck, max_uses: int
) -> str:
    kinds = offered_kinds(inventory)
    charts = chart_hosts(inventory)
    several = multi_chart(inventory)
    trends = trend_figures(inventory)
    rules = ""
    if "cover" in kinds:
        rules += " A first slide of only a title and subtitle is the cover."
    if "closing" in kinds:
        rules += " A closing slide can only be the last one."
    if takeaway_zones(inventory):
        rules += (
            " Takeaways stay in the speaker notes; set show_takeaways: true only when the "
            "user explicitly asks to show the key messages on the slides: a slide listing a "
            "takeaway zone then shows its takeaway there, in place of bullets."
        )
    return (
        "Build a PowerPoint presentation from a plan of slides, on the agent's template. "
        "A NEW deck: write out every slide in `slides`, in order, in ONE call - an eight-slide deck means "
        "eight entries, and the deck holds exactly what you send, not what you planned. Never split a deck "
        "across several calls and never call this tool twice at once. "
        "To CHANGE the last deck of this conversation (a fix after needs_revision, or a change the user asks "
        "for, even on several slides), send only `changes`, numbered on that deck's slides: "
        '{"op": "replace", "slide": N, "slides": [...]}, {"op": "insert", "after": N '
        + "(0 = at the start)"
        + ', "slides": [...]}, {"op": "remove", "slide": N}, {"op": "move", "slide": N, '
        '"after": M}, {"op": "edit", "slide": N, "field": "title" | "bullets[1]" | "items[2].label"'
        + (
            ' | "chart.series[0].values[2]" | "chart.series[0].points[2].y" | '
            '"chart.x_title" | "chart.show" | "chart.highlight"'
            if charts
            else ""
        )
        + (' | "charts[1].series[0].values[2]"' if several else "")
        + ' (indexes from 0), "value": ...}. The other slides stay exactly as they were and the whole deck is rebuilt. '
        "To change text inside a slide, use `edit`: the slide keeps its design; `replace` is for "
        "a different slide (one of the same kind keeps the replaced slide's design when it fits). "
        'When the user wants a slide to look like another ("same layout/design as slide M"), send '
        '{"op": "edit", "slide": N, "field": "like", "value": M}: slide N takes slide M\'s template slide; '
        "resending a slide's current kind or text never changes its design. "
        'Identical consecutive slides the user asked for: {"op": "edit", "slide": N, "field": '
        '"repeat_layout", "value": true}. '
        "For each slide write first its `takeaway` (what the audience concludes, as a sentence; "
        "not on cover, agenda, section, closing and quote slides), then its content: title "
        "(short), subtitle, bullets (telegraphic, "
        "'- ' prefix for a sub-bullet, **bold** allowed), columns [{heading, bullets}], items [{number, "
        "heading, text, label, image"
        + (", trend (up, down or flat: an arrow before the number)" if trends else "")
        + "}], image/images (document_ids from list_images_in_folder), "
        + (
            "table {header, rows} for tabular data (total_row: true when the last row "
            "is a total; highlight_row, highlight_column: the first cell or header of "
            "the one row or column that matters), "
            if "table" in kinds
            else ""
        )
        + (
            "chart {type, categories, series [{name, values}], title, unit, show} for numbers "
            "(data only: the template sets its colours, fonts and place; a pie or doughnut "
            "labels its slices with percentages: to display numbers instead of percentages "
            "on a pie, set show: 'value', or 'both' for the two; to make one category or "
            "series stand out, set highlight to its name, never a colour; sort: 'desc' "
            "puts the largest first; stacked_as: 'percent' shows a stacked_column as "
            "shares of 100 %, stacked_bar too; scatter and bubble take series [{name, "
            "points [{x, y, size, label}]}] with x_title, x_unit, y_title, unit (bubble: "
            "size_title, size_unit) instead of categories and values), "
            if charts
            else ""
        )
        + (
            "charts [chart, …] for several charts on one slide, each with its title "
            "(only on a slide listed with charts×N, exactly N), "
            if several
            else ""
        )
        + "notes, `source` on a slide with figures (document name, 'user', or "
        "'illustrative' only when the user asked for made-up data); then, "
        "optionally, its `kind` from the list below (left out, it is inferred from the content; a kind "
        "the template cannot use there is replaced by a close kind that holds the content, never an "
        "unrelated one). The tool picks the "
        "template slide for each entry. `repeat_layout`: "
        + REPEAT_LAYOUT_HINT
        + rules
        + " A slide holds only the fields its kind lists below (no subtitle on a kind that lists "
        "none, item numbers only where listed). Respect the limits below: a slide is not "
        "a document. If a slide fits no slide of the template, nothing is built and the result lists, per "
        "slide, what to change: apply it with `changes`. The result is shown to the user automatically; "
        "never write a download link. Each call's deck replaces the previous one.\n"
        + _guide(kinds, variety, max_uses, charts, several)
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
    validate_plan = ctx.config.validate_plan
    args_schema = _args_schema(inventory, validate_plan)
    previous_problems: _Previous = {}
    # Variety is asked on the turn's first evaluated plan (one tool instance)
    # only: a call refused before evaluation does not use the ask up.
    called = False
    variety = ctx.config.variety_check
    max_uses = ctx.config.variety_max_uses

    # One build at a time: parallel calls of a round are refused by the
    # middleware, this guards the turn's state when the tool is called directly.
    build_lock = asyncio.Lock()
    # What this turn's `changes` apply to: the deck delivered, or a refused or
    # proposed `slides` plan. A refused `changes` call leaves it as it was, so
    # a later call never builds on changes it did not send. A delivered deck or
    # a proposed plan is stored for later turns, a refused one never.
    turn_base: List[DeckPlan] = []
    # Calls refused this turn, keyed with the plan they applied to: the same
    # call on the same base is refused again without a new evaluation.
    refused_calls: Dict[str, str] = {}
    # The deck delivered this turn and its file name: a `slides` resend of it is
    # answered without a rebuild (same turn only, so the template is the same).
    turn_delivered: List[Tuple[DeckPlan, str]] = []
    plans = _BasePlans(identity.session_id, identity.agent_instance_id)

    async def delivered_before(base: Optional[DeckPlan]) -> bool:
        if turn_delivered or (base is not None and base.delivered):
            return True
        if deck_delivered(history()):
            return True
        try:
            stored = await plans.read() if base is None else None
        except Exception:  # noqa: BLE001 - no proof of a deck: the plan is shown
            logger.warning("[PPTBUILD][TOOL] base plan unreadable", exc_info=True)
            return False
        return stored is not None and stored.delivered

    async def previous_deck(base: Optional[DeckPlan]) -> Optional[DeckPlan]:
        """The deck the user had before this build, if one was delivered."""
        if turn_delivered:
            return turn_delivered[0][0]
        if base is not None and base.delivered:
            return base
        try:
            stored = await plans.read()
        except Exception:  # noqa: BLE001 - the delta line is only a help
            logger.warning("[PPTBUILD][TOOL] base plan unreadable", exc_info=True)
            return None
        return stored if stored is not None and stored.delivered else None

    async def _build(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        async with build_lock:
            return await _build_plan(**kwargs)

    async def _build_plan(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        nonlocal called
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
        base: Optional[DeckPlan] = None
        cleared: Dict[int, List[str]] = {}
        origins: Dict[int, Origin] = {}
        if changes is not None and (changes or not plan.slides):
            if plan.slides:
                has_deck = await delivered_before(None)
                return _error(_BOTH_MODES[0] + _BOTH_MODES[2 if has_deck else 1])
            if not changes:
                return _error(_NO_CHANGE)
            try:
                base = turn_base[0] if turn_base else await plans.read()
            except Exception:  # noqa: BLE001 - the model can resend the whole deck
                logger.warning("[PPTBUILD][TOOL] base plan unreadable", exc_info=True)
                return _error(_BASE_UNREADABLE)
            if base is None:
                return _error(_NO_BASE)
            try:
                changed = apply_changes(
                    base,
                    changes,
                    lambda slide: unplaced(inventory, slide, slide.kind),
                    cleared,
                    origins,
                )
            except ChangeError as exc:
                return _error(
                    "No deck was built: some changes cannot be applied to the previous "
                    "deck (nothing was changed). Fix them and send all the changes again:\n"
                    + "\n".join(exc.problems)
                )
            show = getattr(validated, "show_takeaways", None)
            plan = changed.model_copy(
                update={
                    "file_name": validated.file_name or changed.file_name,
                    "audience": validated.audience or changed.audience,
                    "main_message": validated.main_message or changed.main_message,
                    "show_takeaways": changed.show_takeaways if show is None else show,
                }
            )
            # Rebuilt, an identical deck would read as a change done.
            if (
                base.delivered
                and plan.file_name == base.file_name
                and plan.show_takeaways == base.show_takeaways
                and unchanged(base, plan, _kinds(inventory))
            ):
                return _answer(_UNCHANGED)

        delivered = await previous_deck(None) if base is None else None
        if delivered is not None:
            plan = repinned(delivered, plan, _kinds(inventory))

        call_key = json.dumps(kwargs, sort_keys=True, default=_jsonable) + (
            base.model_dump_json() if base is not None else ""
        )
        if call_key in refused_calls:
            return _answer(_same_call(refused_calls[call_key], base is not None))

        def refused(stored: DeckPlan) -> None:
            if base is None:
                turn_base[:] = [stored]

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
        # Only the slides `changes` touch are checked: an edit is never refused
        # over a slide it leaves as it was.
        kept = {id(s) for s in base.slides} if base is not None else set()
        checked = [n for n, s in enumerate(plan.slides, start=1) if id(s) not in kept]
        # After `checked`: the copies it makes are not slides the call changed.
        plan = _shown_takeaways(plan)
        assignment, plan, bad = await asyncio.to_thread(
            _evaluate,
            inventory,
            plan,
            prefetched,
            variety,
            max_uses,
            checked,
        )
        first, called = not called, True
        unloadable = [
            f"image '{uid}' is not a usable image document and was left out: use a "
            "document_id from list_images_in_folder."
            for uid in bad
        ]
        workspace = services.workspace_fs
        session_id = identity.session_id
        asking = first and variety != "off"
        repeats = [r for r in assignment.repeats if r.revisable] if asking else []
        # `changes` change a deck the conversation has, even when the history
        # sent to the model no longer shows it; read only when an ask would follow.
        if repeats and (base is not None or deck_delivered(history())):
            repeats = []
        # The user validated the plan: its slides stay as they agreed.
        answered = validate_plan and plan_answered(history())
        if answered:
            repeats = []
        if assignment.problems:
            refused(plan)
            refused_calls[call_key] = "; ".join(
                f"slide {_numbered(p.index, origins)}: {p.problem}"
                for p in assignment.problems
            )
            return _needs_revision(
                assignment,
                plan,
                previous_problems,
                repeats,
                unloadable + _cleared_lines(cleared, plan),
                origins if base is not None else None,
            )
        previous_problems.clear()
        if repeats:
            refused(plan)
            return _variety_revision(repeats, assignment)
        if (
            validate_plan
            and not answered
            and not validated.skip_plan
            and not await delivered_before(base)
        ):
            proposed = plan.model_copy(update={"proposed": True, "delivered": False})
            turn_base[:] = [proposed]
            await plans.write(proposed)
            return _proposal(plan, assignment)

        # Stored as delivered: a split list's parts become slides of their own,
        # so the file, the model and later `changes` share one numbering.
        deck, patterns, numbers = assignment.deck(plan)
        deck = deck.model_copy(
            update={
                "delivered": True,
                "slides": [
                    s.model_copy(
                        update={
                            "built_on": p.id if p else None,
                            "asked_design": None,
                            "asked_from": None,
                        }
                    )
                    for s, p in zip(deck.slides, patterns)
                ],
            }
        )
        if base is None and turn_delivered:
            delivered, delivered_name = turn_delivered[0]
            if (
                delivered.file_name == deck.file_name
                and delivered.show_takeaways == deck.show_takeaways
                and unchanged(delivered, deck, _kinds(inventory))
            ):
                return _answer(_already_delivered(delivered_name, len(deck.slides)))

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
        try:
            result = await asyncio.to_thread(
                _prepare_and_render,
                template_bytes,
                inventory,
                deck,
                patterns,
                prefetched,
                numbers,
                assignment.starts,
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
        prints = result.fingerprints
        if len(prints) == len(deck.slides):
            deck = deck.model_copy(
                update={
                    "slides": [
                        s.model_copy(update={"rendered": f})
                        for s, f in zip(deck.slides, prints)
                    ]
                }
            )
        previous = await previous_deck(base)
        delta = (
            ""
            if previous is None
            else deck_delta(previous, deck, _kinds(inventory), base is None, numbers)
        )
        # Delivered, the deck is the base: the same changes sent again are a
        # new change to it, not a corrected resend of a refused one.
        turn_base[:] = [deck]
        turn_delivered[:] = [(deck, file_name)]
        refused_calls.clear()
        await plans.write(deck)

        notes = _build_notes(
            plan,
            result.report.issues(),
            result.report.notes
            + unloadable
            + assignment.notes
            + _cleared_lines(cleared, plan, numbers),
        )
        notes = delta + _designs_line(inventory, patterns) + notes

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
                summary=_summary(
                    result.report.built, sent, bad, numbers, assignment.repeated
                ),
            )
            return (
                f"Delivered: '{file_name}', {result.slide_count} slides. This replaces any deck built earlier "
                "in this answer. A preview opens beside the chat and a download button is shown "
                "automatically; do not write a download link. To change it, send only `changes` numbered "
                f"on the file's slides (1 to {result.slide_count}, a list continued on two slides counts "
                "two); every call rebuilds the whole deck. Describe to the user only what the deck "
                "actually holds: never a change, layout or source it does not show."
                + notes,
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
