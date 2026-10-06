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
import json
import logging
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import CapabilityContext, EmptyModel
from fred_sdk.contracts.context import (
    LinkKind,
    LinkPart,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import WorkspaceFileNotFound, WorkspaceFsPort
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder.assign import (
    Assignment,
    Repeat,
    assign,
    assignable,
)
from fred_capability_ppt_filler.builder.checks import SlideReport
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    SlideKind,
    TemplateInventory,
)
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    PlanTable,
    SlidePlan,
    has_content,
    zone_summary,
)
from fred_capability_ppt_filler.builder.render import RenderError, render_deck
from fred_capability_ppt_filler.concurrency import (
    acquire_heavy_job_slot,
    release_heavy_job_slot,
)
from fred_capability_ppt_filler.fill import (
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
    "The server is busy building other presentations right now. Wait for the other calls to "
    "finish, then make ONE call with the whole deck. Do not send several build calls at once: "
    "each builds a separate presentation and they compete for the same slot."
)


# --- catalogue --------------------------------------------------------------------------


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
    of the JSON schema only: validation accepts anything and coerces it."""
    return _schema_for(tuple(offered_kinds(inventory)))


def _kind_enum(kinds: Tuple[SlideKind, ...]) -> Any:
    """Replace the full `SlideKind` enum the type generates: models read the
    nested `anyOf` and asked for kinds this template does not offer."""

    def extra(schema: Dict[str, Any]) -> None:
        schema.pop("enum", None)
        schema["anyOf"] = [{"type": "string", "enum": list(kinds)}, {"type": "null"}]

    return extra


# Built per turn otherwise: pydantic model creation costs milliseconds of CPU
# on the event loop, and templates share a handful of kind sets.
@lru_cache(maxsize=64)
def _schema_for(kinds: Tuple[SlideKind, ...]) -> type[BaseModel]:
    # Offered only when the template holds a table: the field is noise otherwise.
    table: Any = (
        (Optional[PlanTable], SlidePlan.model_fields["table"])
        if "table" in kinds
        else (SkipJsonSchema[Optional[PlanTable]], None)
    )
    slide_model = create_model(
        "BuildSlide",
        __base__=SlidePlan,
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
    model = create_model(
        "BuildPresentationArgs",
        __base__=BaseModel,
        __config__=ConfigDict(extra="ignore"),
        slides=(
            List[slide_model],
            Field(default_factory=list, description="The slides, in order."),
        ),  # type: ignore[valid-type]
        file_name=(
            Optional[str],
            Field(
                default=None,
                description="Short, relevant file name for the deck; '.pptx' is added.",
            ),
        ),
    )
    return model


def _to_plan(validated: Any) -> DeckPlan:
    return DeckPlan(
        slides=[
            SlidePlan.model_validate(slide.model_dump()) for slide in validated.slides
        ],
        file_name=validated.file_name,
    )


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
    assignment: Assignment, plan: DeckPlan, previous: _Previous
) -> tuple[str, ToolInvocationResult]:
    """The problems, each flagged when the previous call already had it, so the
    model never reads the same message twice without learning what changed."""
    current: _Previous = {}
    slides = []
    for problem in assignment.problems:
        sent = plan.slides[problem.index - 1].model_dump_json()
        entry = problem.as_dict()
        before = previous.get(problem.index)
        if before is not None and before[0] == problem.problem:
            entry["repeated"] = (
                "you resent this slide unchanged: apply one of the options"
                if before[1] == sent
                else "the slide changed but this problem is still there"
            )
        current[problem.index] = (problem.problem, sent)
        slides.append(entry)
    previous.clear()
    previous.update(current)
    payload = {"status": "needs_revision", "slides": slides}
    return _error(
        "No deck was built: some slides fit no slide of this template. Fix each slide listed "
        "below with one of its options, then call build_presentation again with the WHOLE "
        "deck.\n" + json.dumps(payload, ensure_ascii=False)
    )


def _variety_revision(
    repeats: List[Repeat], assignment: Assignment
) -> tuple[str, ToolInvocationResult]:
    """Asked once, on the first deck of a conversation: the repeated slides and
    what each alternative suits; a resend is built as is."""
    kinds = [p.kind if p else None for p in assignment.patterns]
    restated = any(
        kinds[i] in ("two_columns", "comparison") and kinds[i + 1] == "table"
        for r in repeats
        for i in (n - 1 for n in r.slides)
        if i + 1 < len(kinds)
    )
    payload = {
        "status": "needs_revision",
        "variety": [
            {
                "slides": r.slides,
                "template_slide": r.pattern.label,
                "kind": r.pattern.kind,
                "options": [
                    f"another '{r.pattern.kind}' variant: {u}" for u in r.unused
                ]
                + r.others,
            }
            for r in repeats
        ],
    }
    return _error(
        "No deck was built yet: several slides would look the same. Recast some of the slides "
        "listed below into one of their options, rewriting the content in that shape"
        + (
            ", and do not restate a table's content as columns on the slide before it"
            if restated
            else ""
        )
        + ". Then call build_presentation again with the WHOLE deck. If these slides must stay "
        "alike, send the same plan again: it will be built as is.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


async def _deck_delivered(
    workspace: WorkspaceFsPort, session_id: Optional[str]
) -> bool:
    """Whether this conversation already holds a deck: every build is written to
    its outputs folder. Unknown counts as delivered, so it never adds a loop."""
    folder = f"outputs/{session_id}" if session_id else "outputs"
    try:
        entries = await workspace.ls(folder)
    except WorkspaceFileNotFound:
        return False
    except Exception:  # noqa: BLE001 - the passive note still reports it
        logger.warning("[PPTBUILD][TOOL] outputs listing failed", exc_info=True)
        return True
    return any(e.path.lower().endswith(".pptx") and not e.is_dir for e in entries)


def _issue_line(report: SlideReport) -> str:
    parts = []
    if report.truncated:
        parts.append("text cut to fit in " + ", ".join(report.truncated))
    if report.removed:
        parts.append(
            "template example text removed: "
            + ", ".join(f"'{t}'" for t in report.removed)
        )
    if report.lost:
        parts.append("not placed: " + ", ".join(report.lost))
    parts.extend(report.shrunk)
    return f"Slide {report.position}: " + "; ".join(parts) + "."


def _build_notes(plan: DeckPlan, issues: List[SlideReport], notes: List[str]) -> str:
    """What the agent should know about the deck it just built."""
    lines = [
        f"Entry {index} of 'slides' was not a slide object and was skipped."
        for index, slide in enumerate(plan.slides, start=1)
        if slide.invalid_entry is not None
    ]
    lines += [_issue_line(report) for report in issues] + notes
    if not lines:
        return ""
    return (
        "\nTo review (if it matters, call again with the whole corrected deck; the new build "
        "replaces this one):\n" + "\n".join(lines)
    )


async def _no_images() -> Dict[str, object]:
    return {}


def _prepare_and_render(
    template_bytes: bytes,
    inventory: TemplateInventory,
    plan: DeckPlan,
    patterns: List[Any],
    prefetched: Dict[str, object],
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
    return render_deck(template_bytes, inventory, plan, patterns, images)


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
            return f"The folder '{normalized}' holds no image."
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


def _description(inventory: TemplateInventory) -> str:
    kinds = offered_kinds(inventory)
    rules = ""
    if "cover" in kinds:
        rules += " The first slide is always the template's cover."
    if "closing" in kinds:
        rules += " A closing slide can only be the last one."
    return (
        "Build a PowerPoint presentation from a plan of slides, on the agent's template. "
        "ONE call builds the WHOLE deck: write out every slide of the presentation in `slides`, in order, in "
        "a single call - an eight-slide deck means eight entries, and the deck holds exactly what you send, "
        "not what you planned. Never split a deck across several calls and never call this tool twice at "
        "once: each call produces a complete presentation of its own, so splitting delivers several truncated "
        "decks instead of one. For each slide write its content: title, subtitle, bullets (telegraphic, "
        "'- ' prefix for a sub-bullet, **bold** allowed), columns [{heading, bullets}], items [{number, "
        "heading, text, label, image}], image/images (document_ids from list_images_in_folder), "
        + ("table {header, rows} for tabular data, " if "table" in kinds else "")
        + "notes; then, "
        "optionally, its `kind` from the list below (left out, it is inferred from the content; a kind "
        "the template cannot use there is replaced by one that holds the content). The tool picks the "
        "template slide for each entry."
        + rules
        + " A slide holds only the fields its kind lists below (no subtitle on a kind that lists "
        "none, item numbers only where listed). Respect the limits below: a slide is not "
        "a document. If a slide fits no slide of the template, nothing is built and the result lists, per "
        "slide, what to change: apply it and call again with the whole deck. The result is shown to the "
        "user automatically; never write a download link. To correct a deck, call again once with the "
        "whole amended plan; the new deck replaces the previous one.\n"
        " Vary the content shapes across the deck - items, columns, figures, a quote - rather than "
        "bullets everywhere: each variant below is a different template slide, and the deck "
        "looks best when it uses many of them.\n"
        "Slide kinds of this template, with each variant's name and what each zone holds at full "
        "size (≈chars per line × lines; items max N; variants separated by |). Write to these sizes:\n"
        + catalogue(inventory)
    )


def build_builder_tools(
    ctx: "CapabilityContext[PptBuilderConfig, EmptyModel]",
    template_bytes_loader,
    inventory: TemplateInventory,
) -> list[BaseTool]:
    """The build tool bound to one turn's context and effective inventory.

    ``template_bytes_loader`` is an async callable returning the template
    bytes (the stored asset, or the built-in template).
    """
    services = ctx.services
    identity = ctx.identity
    args_schema = _args_schema(inventory)
    previous_problems: _Previous = {}
    # Variety is asked at most once per tool instance; the next call is built.
    variety_asked = False

    async def _build(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        nonlocal variety_asked
        try:
            plan = _to_plan(args_schema(**kwargs))
        except Exception as exc:  # noqa: BLE001 - coercion makes this unexpected
            logger.warning("[PPTBUILD][TOOL] unreadable plan: %s", exc)
            return _error(
                "The slide plan could not be read. Call build_presentation again with 'slides' as a "
                "list of objects, each with its content (title, bullets, items…)."
            )

        if not any(has_content(s) for s in plan.slides if s.invalid_entry is None):
            return _error(
                "The plan has no content, so nothing was generated. Write the slides (title, bullets, "
                "items…) and call build_presentation again."
            )
        # Before any I/O: a plan that needs revision costs no template fetch.
        assignment = await asyncio.to_thread(assign, inventory, plan)
        if assignment.problems:
            return _needs_revision(assignment, plan, previous_problems)
        previous_problems.clear()

        workspace = services.workspace_fs
        if workspace is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.workspace_fs is not available on this execution path."
            )
        session_id = identity.session_id
        # Listed only when a revision would follow: the usual call adds no I/O.
        repeats = [r for r in assignment.repeats if r.revisable]
        if (
            repeats
            and not variety_asked
            and not await _deck_delivered(workspace, session_id)
        ):
            variety_asked = True
            return _variety_revision(repeats, assignment)
        image_ids = _image_ids(plan)
        if image_ids and services.document_content is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.document_content is not available on this execution path."
            )

        started = time.monotonic()
        # The template fetch and the image prefetch are independent I/O.
        try:
            template_bytes, prefetched = await asyncio.gather(
                template_bytes_loader(),
                _prefetch_image_bytes(image_ids, services)
                if image_ids
                else _no_images(),
            )
        except Exception:  # noqa: BLE001 - surfaced to the agent
            logger.exception("[PPTBUILD][TOOL] template load FAILED")
            return _error(
                "The presentation template could not be loaded right now. Tell the user and suggest trying "
                "again in a moment."
            )

        if not acquire_heavy_job_slot():
            return _error(_BUSY_MESSAGE)
        try:
            result = await asyncio.to_thread(
                _prepare_and_render,
                template_bytes,
                inventory,
                plan,
                assignment.patterns,
                prefetched,
            )
        except RenderError as exc:
            return _error(f"{exc} Check the plan and call build_presentation again.")
        except Exception:  # noqa: BLE001 - wrapped uniformly for the agent
            elapsed = time.monotonic() - started
            logger.exception("[PPTBUILD][TOOL] render FAILED after %.0fs", elapsed)
            return _error(
                "The presentation could not be built because of an internal problem. Tell the user and "
                "suggest trying again; if it persists, simplify the plan."
            )
        finally:
            release_heavy_job_slot()

        file_name = (
            _sanitize_output_file_name(plan.file_name)
            if plan.file_name
            else _DEFAULT_FILE_NAME
        )
        # Keyed by the deck's name, deliberately. A model that splits one deck
        # across several calls, or retries after a busy answer, then lands on
        # one key and the reader sees one presentation instead of a card per
        # fragment. A genuinely different deck gets a different name from the
        # model, and with it its own key.
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
                "The presentation was built but could not be saved to the conversation files. Tell the "
                "user and suggest trying again in a moment."
            )

        notes = _build_notes(plan, result.report.issues(), assignment.notes)

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
            )
            return (
                f"Delivered: '{file_name}', {result.slide_count} slides. This replaces any deck built earlier "
                "in this answer. A preview opens beside the chat and a download button is shown "
                "automatically; do not write a download link. Every call rebuilds the whole deck: to add "
                "or fix slides, call again with the COMPLETE list, never only the missing ones. Describe "
                "to the user only the slides the deck actually holds." + notes,
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
            "generated, only the download). A download button is shown automatically; do not write a link."
            + notes,
            ToolInvocationResult(tool_ref=_TOOL_REF, ui_parts=(cast_ui_part(link),)),
        )

    description = _description(inventory)
    build_tool = StructuredTool.from_function(
        coroutine=_build,
        name=BUILD_TOOL_NAME,
        description=description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )
    return [build_tool, build_list_images_tool(ctx)]
