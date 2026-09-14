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
shared PDF preview part. The ``pattern`` field of the plan is a closed enum
built from the effective inventory, so the model cannot name a pattern that
does not exist.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import CapabilityContext, EmptyModel
from fred_sdk.contracts.context import LinkKind, LinkPart, ToolInvocationResult
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from fred_capability_ppt_filler.builder.models import (
    INTENTS,
    Pattern,
    TemplateInventory,
)
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    PlanColumn,
    PlanItem,
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

_BUSY_MESSAGE = "The server is busy building other presentations right now. Please try again in a moment."


# --- catalogue --------------------------------------------------------------------------


def _zone_summary(pattern: Pattern) -> str:
    parts: List[str] = []
    seen: set[str] = set()
    for zone in pattern.zones:
        if zone.role in ("keep", "image") or zone.role in seen:
            continue
        seen.add(zone.role)
        limit = f" ≤{zone.max_chars} chars" if zone.max_chars else ""
        lines = (
            f" ≤{zone.max_lines} lines" if zone.max_lines and zone.max_lines > 1 else ""
        )
        count = sum(1 for z in pattern.zones if z.role == zone.role)
        parts.append(
            f"{zone.role}{'×' + str(count) if count > 1 else ''}{limit}{lines}"
        )
    images = sum(1 for z in pattern.zones if z.role == "image")
    if images:
        parts.append(f"images×{images}")
    for group in pattern.groups:
        roles = ", ".join(r for r in group.item_zones if r != "keep")
        parts.append(f"items×{group.count} [{roles}]")
    return "; ".join(parts) or "no editable zone"


def catalogue(inventory: TemplateInventory) -> str:
    """One line per usable pattern, for the tool description."""
    lines = []
    for pattern in included_patterns(inventory):
        star = " (preferred)" if pattern.preferred else ""
        lines.append(
            f'- {pattern.id} [{pattern.intent}]{star} "{pattern.label}": {_zone_summary(pattern)}'
        )
    return "\n".join(lines)


def _args_schema(inventory: TemplateInventory) -> type[BaseModel]:
    """``DeckPlan`` with ``pattern`` closed over the usable ids and the intents."""
    choices = tuple(p.id for p in included_patterns(inventory)) + INTENTS
    slide_model = create_model(
        "BuildSlide",
        __base__=SlidePlan,
        pattern=(
            Literal[choices],  # type: ignore[valid-type]
            Field(
                description="A pattern id from the catalogue, or an intent name (resolved to the best pattern)."
            ),
        ),
    )
    return create_model(
        "BuildPresentationArgs",
        __base__=BaseModel,
        slides=(List[slide_model], Field(description="The slides, in order.")),  # type: ignore[valid-type]
        file_name=(
            Optional[str],
            Field(
                default=None,
                description="Short, relevant file name for the deck; '.pptx' is added.",
            ),
        ),
    )


def _to_plan(validated: BaseModel) -> DeckPlan:
    dumped = validated.model_dump()
    return DeckPlan(
        slides=[
            SlidePlan(
                pattern=s["pattern"],
                title=s.get("title"),
                subtitle=s.get("subtitle"),
                bullets=s.get("bullets") or [],
                columns=[PlanColumn(**c) for c in s.get("columns") or []],
                items=[PlanItem(**i) for i in s.get("items") or []],
                image=s.get("image"),
                images=s.get("images") or [],
                notes=s.get("notes"),
            )
            for s in dumped["slides"]
        ],
        file_name=dumped.get("file_name"),
    )


def _image_ids(plan: DeckPlan) -> set[str]:
    ids: set[str] = set()
    for slide in plan.slides:
        if slide.image:
            ids.add(slide.image)
        ids.update(i for i in slide.images if i)
        ids.update(item.image for item in slide.items if item.image)
    return ids


class _BadImage(ValueError):
    def __init__(self, document_id: str, reason: str) -> None:
        super().__init__(reason)
        self.document_id = document_id


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
    thread: Pillow decoding a large WEBP is hundreds of milliseconds of CPU."""
    images = {}
    for document_id, raw in prefetched.items():
        try:
            images[document_id] = prepare_picture(raw)  # type: ignore[arg-type]
        except NotAnImageError as exc:
            raise _BadImage(document_id, str(exc)) from exc
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
        except Exception as exc:  # noqa: BLE001 - the model's malformed call
            return f"Invalid plan: {exc}", ToolInvocationResult(
                tool_ref=_TOOL_REF, is_error=True
            )

        if not plan.slides or not any(
            has_content(s) or _is_fixed(inventory, s.pattern) for s in plan.slides
        ):
            return (
                "The plan has no content — nothing was generated. Write the slides first (title, bullets, "
                "items) then call this tool again.",
                ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
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
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent
            message = f"Could not load the presentation template [{type(exc).__name__}: {exc}]."
            logger.exception("[PPTBUILD][TOOL] template load FAILED -> %s", message)
            return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)
        for document_id, fetched in prefetched.items():
            if isinstance(fetched, Exception):
                return (
                    f"Could not fetch the image document '{document_id}' [{type(fetched).__name__}: {fetched}]. "
                    "List the folder again with list_images_in_folder and pass a valid document_id.",
                    ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                )

        if not acquire_heavy_job_slot():
            return _BUSY_MESSAGE, ToolInvocationResult(
                tool_ref=_TOOL_REF, is_error=True
            )
        try:
            result = await asyncio.to_thread(
                _prepare_and_render, template_bytes, inventory, plan, prefetched
            )
        except _BadImage as exc:
            return (
                f"The document '{exc.document_id}' is not a usable image [{exc}]. Pick an image document.",
                ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
            )
        except RenderError as exc:
            return str(exc), ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)
        except Exception as exc:  # noqa: BLE001 - wrapped uniformly for the agent
            elapsed = time.monotonic() - started
            message = f"Could not build the presentation after {elapsed:.0f}s [{type(exc).__name__}: {exc}]."
            logger.exception("[PPTBUILD][TOOL] render FAILED -> %s", message)
            return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)
        finally:
            release_heavy_job_slot()

        file_name = (
            _sanitize_output_file_name(plan.file_name)
            if plan.file_name
            else _DEFAULT_FILE_NAME
        )
        session_id = identity.session_id
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
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent
            message = f"Built the presentation but could not upload it [{type(exc).__name__}: {exc}]."
            logger.exception("[PPTBUILD][TOOL] upload FAILED -> %s", message)
            return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)

        notes = ""
        if result.warnings:
            notes = " Notes: " + " ".join(result.warnings)

        pdf_bytes = await convert_office_bytes_to_pdf(result.pptx, suffix=".pptx")
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
                file_name=pptx_artifact.file_name,
            )
            return (
                f"The presentation '{file_name}' ({result.slide_count} slides) is ready. A preview opens beside "
                "the chat and a download button is shown automatically; do not write a download link."
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
            "generated, only the download). A download button is shown automatically; do not write a link."
            + notes,
            ToolInvocationResult(tool_ref=_TOOL_REF, ui_parts=(cast_ui_part(link),)),
        )

    description = (
        "Build a PowerPoint presentation from a plan of slides, on the agent's template. Each slide names a "
        "pattern (id below, or an intent name) and gives its content: title, subtitle, bullets (telegraphic, "
        "'- ' prefix for a sub-bullet, **bold** allowed), columns [{heading, bullets}], items [{number, "
        "heading, text, label, image}] for patterns with items, image/images (document_ids from "
        "list_images_in_folder), notes. Respect the character limits: a slide is not a document. Start with a "
        "'title' slide and end with a 'fixed' closing slide when one exists. The result is shown to the user "
        "automatically; never write a download link. To correct a deck, call again with the amended plan.\n"
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
