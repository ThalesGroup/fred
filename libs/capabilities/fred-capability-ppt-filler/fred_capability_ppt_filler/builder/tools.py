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

The tool never lets a malformed call fail validation: the schema the model
sees lists the pattern ids as an enum, but the arguments are coerced and every
slide resolves to a pattern (see ``plan.resolve``). What cannot be honoured is
reported to the agent in the result, and every error result carries its text
so the user sees it instead of an opaque failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, cast

from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import CapabilityContext, EmptyModel
from fred_sdk.contracts.context import (
    LinkKind,
    LinkPart,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model

from fred_capability_ppt_filler.builder.models import (
    INTENTS,
    Pattern,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.plan import (
    ITEM_FIELDS,
    SLIDE_FIELDS,
    DeckPlan,
    SlidePlan,
    has_content,
    included_patterns,
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


# The catalogue names the plan field a zone is filled from, not the zone's role:
# a model copies these names into the plan, and a role name it cannot map to a
# field is content silently lost. Shared with the pattern scoring, so what the
# agent is offered and what a pattern is picked for cannot diverge.
_SLIDE_FIELDS = SLIDE_FIELDS
_ITEM_FIELDS = ITEM_FIELDS


def _limit(zones: Sequence[Zone]) -> str:
    """The room the agent can count on across zones filled from one field: the
    tightest one, since that is the zone that truncates.

    A zone that grows with its text has no limit to quote — its box is sized to
    the designer's sample, and a figure twice as long simply widens it.
    """
    bounded = [z for z in zones if not z.grows]
    if not bounded:
        return ""
    chars = [z.max_chars for z in bounded if z.max_chars]
    lines = [z.max_lines for z in bounded if z.max_lines]
    text = f" ≤{min(chars)} chars" if chars else ""
    if lines and min(lines) > 1:
        text += f" ≤{min(lines)} lines"
    return text


def _zone_summary(pattern: Pattern) -> str:
    if pattern.intent == "fixed":
        return "used as is, no editable zone (content given for it is ignored)"
    parts: List[str] = []
    seen: set[str] = set()
    for zone in pattern.zones:
        field = _SLIDE_FIELDS.get(zone.role)
        if field is None or field in seen:
            continue
        seen.add(field)
        same = [z for z in pattern.zones if _SLIDE_FIELDS.get(z.role) == field]
        # Several body zones are columns, and only `columns` reaches them: named
        # `bullets×3`, the field the agent then sends fills the first and the
        # other two stay empty.
        if field == "bullets" and len(same) > 1:
            field = "columns.bullets"
        count = f"×{len(same)}" if len(same) > 1 else ""
        parts.append(f"{field}{count}{_limit(same)}")
    images = sum(1 for z in pattern.zones if z.role == "image")
    if images:
        parts.append(f"images×{images}")
    for group in pattern.groups:
        fields: Dict[str, List[Zone]] = {}
        for item in group.items:
            for zone in item:
                field = _ITEM_FIELDS.get(zone.role)
                if field:
                    fields.setdefault(field, []).append(zone)
        shown = ", ".join(
            name + ("" if name == "image" else _limit(zones))
            for name, zones in fields.items()
        )
        # "up to", not "×N": told `items×8`, an agent pads a five-point agenda
        # to eight.
        parts.append(f"items up to {group.count} [{shown}]")
    return "; ".join(parts) or "no editable zone"


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    """An error result whose text is Fred-owned, so the runtime shows it."""
    return message, ToolInvocationResult(
        tool_ref=_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def catalogue(inventory: TemplateInventory) -> str:
    """One line per usable pattern, for the tool description."""
    lines = []
    for pattern in included_patterns(inventory):
        # Inventories analysed before fixed slides stopped being preferred still carry it.
        star = " (preferred)" if pattern.preferred and pattern.intent != "fixed" else ""
        lines.append(
            f'- {pattern.id} [{pattern.intent}]{star} "{pattern.label}": {_zone_summary(pattern)}'
        )
    return "\n".join(lines)


def _args_schema(inventory: TemplateInventory) -> type[BaseModel]:
    """The deck plan, with the usable pattern ids and intents listed as an enum
    in the JSON schema only: validation accepts any string and resolves it."""
    choices = [p.id for p in included_patterns(inventory)] + list(INTENTS)
    slide_model = create_model(
        "BuildSlide",
        __base__=SlidePlan,
        pattern=(
            str,
            Field(
                default="",
                description=(
                    "A pattern id copied exactly from the catalogue, or an intent name "
                    "(the tool picks the best pattern for it)."
                ),
                json_schema_extra={"enum": cast(Any, choices)},
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


def _is_fixed(inventory: TemplateInventory, requested: str) -> bool:
    if requested == "fixed":
        return True
    pattern = inventory.pattern(requested)
    return pattern is not None and pattern.intent == "fixed"


async def _no_images() -> Dict[str, object]:
    return {}


def _prepare_and_render(
    template_bytes: bytes,
    inventory: TemplateInventory,
    plan: DeckPlan,
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
    return render_deck(template_bytes, inventory, plan, images)


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


def build_builder_tools(
    ctx: "CapabilityContext[PptBuilderConfig, EmptyModel]",
    template_bytes_loader,
    inventory: TemplateInventory,
) -> list[BaseTool]:
    """The build tool bound to one turn's context and effective inventory.

    ``template_bytes_loader`` is an async callable returning the template
    bytes (the stored asset, or the built-in theme).
    """
    services = ctx.services
    identity = ctx.identity
    args_schema = _args_schema(inventory)

    async def _build(**kwargs: object) -> tuple[str, ToolInvocationResult]:
        try:
            plan = _to_plan(args_schema(**kwargs))
        except Exception as exc:  # noqa: BLE001 - coercion makes this unexpected
            logger.warning("[PPTBUILD][TOOL] unreadable plan: %s", exc)
            return _error(
                "The slide plan could not be read. Call build_presentation again with 'slides' as a "
                "list of objects, each with a 'pattern' and its content (title, bullets, items…)."
            )

        usable = [s for s in plan.slides if s.invalid_entry is None]
        if not usable or not any(
            has_content(s) or _is_fixed(inventory, s.pattern) for s in usable
        ):
            return _error(
                "The plan has no content, so nothing was generated. Write the slides (title, bullets, "
                "items…) and call build_presentation again."
            )

        workspace = services.workspace_fs
        if workspace is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.workspace_fs is not available on this execution path."
            )
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
                _prepare_and_render, template_bytes, inventory, plan, prefetched
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
        session_id = identity.session_id
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

        notes = ""
        if result.warnings:
            notes = (
                "\nAdjustments made (fix the plan and call again if they matter): "
                + " ".join(result.warnings)
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
            )
            return (
                f"Delivered: '{file_name}', {result.slide_count} slides. This replaces any deck built earlier "
                "in this answer. A preview opens beside the chat and a download button is shown "
                f"automatically; do not write a download link.\nCheck that count: if the deck you planned has "
                f"more than {result.slide_count} slides, call once more with the COMPLETE list of slides - "
                "every call rebuilds the whole deck, so sending only the missing ones would throw the rest "
                f"away. If {result.slide_count} is the deck you meant, do not call again: describe it to the "
                "user, and describe only the slides it actually holds." + notes,
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

    description = (
        "Build a PowerPoint presentation from a plan of slides, on the agent's template. "
        "ONE call builds the WHOLE deck: write out every slide of the presentation in `slides`, in order, in "
        "a single call - an eight-slide deck means eight entries, and the deck holds exactly what you send, "
        "not what you planned. Never split a deck across several calls and never call this tool twice at "
        "once: each call produces a complete presentation of its own, so splitting delivers several truncated "
        "decks instead of one. Each slide names a "
        "pattern and gives its content. The simplest reliable pattern value is an intent name (title, section, "
        "agenda, content, two_columns, comparison, image_text, cards, steps, statement, contact, fixed): the "
        "tool picks the template's best slide for it. To use a specific slide of the catalogue, copy its id "
        "exactly (ids like 'slide:259' are internal ids, not slide numbers). Content: title, subtitle, bullets (telegraphic, "
        "'- ' prefix for a sub-bullet, **bold** allowed), columns [{heading, bullets}], items [{number, "
        "heading, text, label, image}] for patterns with items, image/images (document_ids from "
        "list_images_in_folder), notes. Respect the character limits: a slide is not a document. Start with a "
        "'title' slide and end with a 'fixed' closing slide when one exists. The result is shown to the user "
        "automatically; never write a download link. To correct a deck, call again once with the whole "
        "amended plan; the new deck replaces the previous one.\n"
        "Patterns of this template:\n" + catalogue(inventory)
    )
    build_tool = StructuredTool.from_function(
        coroutine=_build,
        name=BUILD_TOOL_NAME,
        description=description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )
    return [build_tool, build_list_images_tool(ctx)]
