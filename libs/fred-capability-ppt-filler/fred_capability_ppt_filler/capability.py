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

"""`PptFillerCapability` — the ppt_filler feature as ONE capability (#1903).

Why this module exists:
- Kea shipped this feature scattered across an inprocess-toolkit factory, a
  `ToolParams` union entry, a bespoke `ToolkitAssetProcessor` seam, and ad-hoc
  controller endpoints. On Swift the WHOLE feature is this one
  `AgentCapability` (RFC AGENT-CAPABILITY-RFC.md §1–§3): manifest (declared
  upload slot, custom form widget, contributed chat part, side panel, analyze
  router) + save-time `validate_config` + chat-time fill middleware.

The uploaded template is the single source of truth (Kea RFC
PPT-FILLER-TOOLKIT-RFC.md): the per-slide schema is always recomputed
server-side from the actual `.pptx` in `validate_config`, and the binary is
stored through the `agent_assets` port — only its key is persisted (RFC §3.8,
never a blob in tuning_json).

Save-time state machine (ports of Kea's `PptFillerAssetProcessor` three
states, re-seated on `validate_config(config, uploads, ctx)`):

================================ ============================================
 Incoming state                   Action
================================ ============================================
 upload in the `template` slot    parse → resolve image folders → on errors
                                  raise (→ uniform 422) → store blob under the
                                  fixed key → persist the recomputed schema
 no upload, schema present        no-op pass-through (ordinary edit)
 no upload, no schema             reject — the template is mandatory
================================ ============================================

The `template` slot declares `min_count=0` on purpose: the PLATFORM slot gate
(RFC §3.4) runs on every save, and a `min_count=1` slot would force re-upload
on every ordinary edit. Mandatory-ness is a CONTENT rule owned here (state 3),
exactly like Kea's `asset_required`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import List

from fastapi import APIRouter, File, UploadFile
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetSlot,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    SaveContext,
    SidePanelSpec,
    UploadedFile,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from fred_capability_ppt_filler.fill import PptPreviewPart, build_fill_tools
from fred_capability_ppt_filler.folder_resolution import (
    FolderResolver,
    resolve_and_validate_images,
)
from fred_capability_ppt_filler.parser import (
    ParseResult,
    SlideSchema,
    TemplateError,
    parse,
)

logger = logging.getLogger(__name__)

PPT_FILLER_CAPABILITY_ID = "ppt_filler"

# Fixed per-instance storage key for the one template (Kea convention: one
# template per agent; replacing it swaps the template).
PPT_FILLER_TEMPLATE_KEY = "ppt_filler_template.pptx"

# The manifest's one upload slot; `validate_config` reads uploads[TEMPLATE_SLOT].
TEMPLATE_SLOT = "template"

# Stable error codes for non-per-slide rejections, reusing the
# `{slide, key, code, message}` shape with slide=0/key="" (same as Kea).
CODE_ASSET_REQUIRED = "asset_required"
CODE_INVALID_UPLOAD = "invalid_upload"

_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


class PptFillerConfig(BaseModel):
    """
    Stored config of the ppt_filler capability (ConfigModel == StoredConfigModel).

    The form never edits these values directly: `schema_slides` is the
    server-recomputed per-slide schema (round-tripped verbatim on ordinary
    edits so a no-upload save passes state 2), and `template_key` is the fixed
    storage key of the uploaded `.pptx` in the instance's config-asset area.
    The template BYTES never appear here (RFC §3.8).
    """

    template_key: str = PPT_FILLER_TEMPLATE_KEY
    schema_slides: List[SlideSchema] = []


class _PortFolderResolver:
    """Adapt the `document_folders` runtime port to the core `FolderResolver` seam."""

    def __init__(self, port) -> None:
        self._port = port

    async def resolve(self, folder: str) -> str | None:
        return await self._port.resolve_folder(folder)


def _format_template_errors(errors: Sequence[TemplateError]) -> str:
    """One human-readable line per structured error (the uniform-422 detail).

    The inline form runs the structured `/analyze` preview BEFORE saving, so
    this string is the defensive backstop, not the primary UX (RFC #1974
    "typed 422 is the existing convention, not a structured envelope").
    """
    return "The PowerPoint template is misconfigured: " + " | ".join(
        error.message for error in errors
    )


def _build_ppt_filler_router() -> APIRouter:
    """The capability's own routes (RFC §3.4: analyze is just a route here)."""

    router = APIRouter(tags=["ppt_filler"])

    @router.post("/analyze", response_model=ParseResult)
    async def analyze(file: UploadFile = File(...)) -> ParseResult:
        """Stateless template analysis for inline pre-save feedback.

        Returns `200 {schema, errors}` — schema and errors TOGETHER so the
        form can preview the extracted fields next to the problems to fix.
        Stores nothing. Offline checks only: folder existence
        (`folder_not_found`) needs platform access and is enforced by the
        save round-trip; every other error code is reported here.
        """
        content = await file.read()
        try:
            result = parse(content)
            # resolver=None: skip the folder→tag lookup (no platform access on
            # this stateless route) but keep the pure geometry check.
            return await resolve_and_validate_images(content, result, None)
        except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a template error
            return ParseResult(
                schema=[],
                errors=[
                    TemplateError(
                        slide=0,
                        key="",
                        code=CODE_INVALID_UPLOAD,
                        message=(
                            f"The uploaded file could not be read as a .pptx: {exc}"
                        ),
                    )
                ],
            )

    return router


# Non-negotiable behavioral fragment delivered whenever the instance has a
# configured template (same prompt-fragment delivery path as the MCP
# capabilities' `agent_instructions`, #1978 AC4). Without it, models treat
# "generate the slides" as an open-ended request and ask the user to upload a
# template that is ALREADY configured server-side.
_FILL_INSTRUCTIONS = (
    "PPT FILLER: this agent already has a PowerPoint template configured by "
    "its owner — NEVER ask the user to upload, name, or provide a template. "
    "When the user asks to produce, generate, or fill the deck/slides, call "
    "the 'fill_ppt_template' tool: each of its fields describes what to put "
    "there — derive the values from the conversation and, when a field "
    "description points at documents, from the document tools (search, "
    "summarize, tree) before calling. Only ask the user for values you "
    "genuinely cannot derive."
)


class _PptFillerMiddleware(AgentMiddleware):
    """Carries the fill tools, bound to the instance's typed stored config,
    and overlays the fill instructions on the system prompt while a template
    is configured (mirrors `_McpInstructionsMiddleware`)."""

    def __init__(self, ctx: CapabilityContext[PptFillerConfig, EmptyModel]) -> None:
        super().__init__()
        self.tools = build_fill_tools(ctx)
        self._fragment = _FILL_INSTRUCTIONS if self.tools else ""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if not self._fragment:
            return await handler(request)
        base = request.system_prompt or ""
        merged = f"{base}\n\n{self._fragment}" if base else self._fragment
        request = request.override(system_message=SystemMessage(content=merged))
        return await handler(request)


class PptFillerCapability(
    AgentCapability[PptFillerConfig, PptFillerConfig, EmptyModel]
):
    """
    Fill an uploaded PowerPoint template from chat (#1903, Kea
    PPT-FILLER-TOOLKIT-RFC.md + images / text-formatting / preview-pane
    extensions). See the module docstring for the save-time state machine.
    """

    manifest = CapabilityManifest(
        id=PPT_FILLER_CAPABILITY_ID,
        version="0.1.0",
        name="capability.ppt_filler.name",
        description="capability.ppt_filler.description",
        icon="slideshow",
        config_fields=[
            # One field owned end-to-end by the plugin's custom form widget
            # (RFC §9 item 4): upload control + inline analyze preview +
            # slide-numbered errors. The generic renderer never sees it.
            FieldSpec(
                key="schema_slides",
                type="array",
                title="PowerPoint template",
                description=(
                    "Template fields extracted per slide from the uploaded "
                    ".pptx (recomputed server-side on every upload)."
                ),
                ui=UIHints(widget="ppt_filler_template"),
            ),
        ],
        assets=[
            AssetSlot(
                key=TEMPLATE_SLOT,
                accepted_types=[".pptx"],
                # min_count=0 so ordinary edits (no re-upload) pass the
                # platform slot gate; the mandatory-template rule is state 3 of
                # validate_config (see module docstring).
                min_count=0,
                max_count=1,
            )
        ],
        chat_parts=[PptPreviewPart],
        side_panels=[SidePanelSpec(widget="ppt_preview_pane")],
        router=_build_ppt_filler_router(),
    )
    ConfigModel = PptFillerConfig

    async def validate_config(
        self,
        config: PptFillerConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> PptFillerConfig:
        template_uploads = list(uploads.get(TEMPLATE_SLOT, ()))

        # --- State 1: upload present → parse, resolve, store blob, persist schema.
        if template_uploads:
            pptx_bytes = template_uploads[0].content
            try:
                result = parse(pptx_bytes)
            except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a 422 reject
                raise ValueError(
                    f"The uploaded file could not be read as a .pptx: {exc}"
                ) from exc

            # Space-aware folder resolution + image-location validation. The
            # resolver rides the save services; a save path without the port
            # must fail LOUD when the template actually uses image folders —
            # never silently skip validation (RFC §3.9).
            folder_port = ctx.services.document_folders
            needs_resolution = any(
                key_field.type == "image" and key_field.folder
                for slide_schema in result.slides
                for key_field in slide_schema.keys
            )
            resolver: FolderResolver | None = None
            if folder_port is not None:
                resolver = _PortFolderResolver(folder_port)
            elif needs_resolution:
                raise RuntimeError(
                    "ppt_filler: RuntimeServices.document_folders is not "
                    "available on this save path, but the template declares "
                    "image folders."
                )
            result = await resolve_and_validate_images(pptx_bytes, result, resolver)
            if result.errors:
                raise ValueError(_format_template_errors(result.errors))

            assets = ctx.services.agent_assets
            if assets is None:
                raise RuntimeError(
                    "ppt_filler: RuntimeServices.agent_assets is not available "
                    "on this save path; the template cannot be stored."
                )
            await assets.store(
                config.template_key,
                pptx_bytes,
                content_type=_PPTX_CONTENT_TYPE,
                filename=config.template_key,
            )
            return config.model_copy(update={"schema_slides": list(result.slides)})

        # --- State 2: no upload, schema present → ordinary edit, pass through.
        if config.schema_slides:
            return config

        # --- State 3: no upload, no schema → the template is mandatory.
        raise ValueError(
            "PPT Filler requires a PowerPoint template, but none was provided "
            "and none is configured. Upload a .pptx template."
        )

    def middleware(
        self, ctx: CapabilityContext[PptFillerConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_PptFillerMiddleware(ctx)]
