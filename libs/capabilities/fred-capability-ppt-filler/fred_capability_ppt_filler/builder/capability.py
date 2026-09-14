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

"""``PptBuilderCapability`` — generate a deck from a chat plan on an analysed
template, or on the built-in theme when the agent has none.

Save-time states of ``validate_config``:

================================ ============================================
 Incoming state                   Action
================================ ============================================
 upload in the `template` slot    analyse → on errors raise (→ 422) → store
                                  the bytes and a patterns PDF (thumbnails)
                                  → keep the overrides that still match
 no upload, inventory present     ordinary edit: prune the overrides, pass
 no upload, no inventory          built-in theme: prune the overrides
================================ ============================================

The stored config carries the inventory and the overrides, never the bytes
(RFC §3.8). The preview chat part and side pane are ``ppt_filler``'s: both
capabilities ship in this package, and a chat-part kind has one owner.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from fred_core import convert_office_bytes_to_pdf
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

from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.models import (
    AnalysisError,
    AnalyzeResult,
    PatternOverride,
    TemplateInventory,
)
from fred_capability_ppt_filler.builder.overrides import (
    apply_overrides,
    prune_overrides,
)
from fred_capability_ppt_filler.builder.preview import build_patterns_deck
from fred_capability_ppt_filler.builder.theme import default_theme
from fred_capability_ppt_filler.builder.tools import build_builder_tools
from fred_capability_ppt_filler.capability import (
    CODE_INVALID_UPLOAD,
    CODE_SERVER_BUSY,
    MAX_TEMPLATE_UPLOAD_BYTES,
    TEMPLATE_SLOT,
)
from fred_capability_ppt_filler.concurrency import (
    acquire_heavy_job_slot,
    release_heavy_job_slot,
)

logger = logging.getLogger(__name__)

PPT_BUILDER_CAPABILITY_ID = "ppt_builder"
PPT_BUILDER_TEMPLATE_KEY = "ppt_builder_template.pptx"
PPT_BUILDER_PATTERNS_KEY = "ppt_builder_patterns.pdf"

_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
_PDF_CONTENT_TYPE = "application/pdf"
_BUSY_MESSAGE = "The server is busy analysing other PowerPoint templates right now. Please try again in a moment."


class PptBuilderConfig(BaseModel):
    """Stored config (ConfigModel == StoredConfigModel).

    ``inventory`` is recomputed from the real bytes at every upload; ``None``
    means the agent builds on the built-in theme. ``patterns_path`` is the
    Knowledge Flow path of the thumbnails PDF stored beside the template, so
    the form can fetch it with the user's bearer without a proxy route.
    """

    template_key: str = PPT_BUILDER_TEMPLATE_KEY
    patterns_key: str = PPT_BUILDER_PATTERNS_KEY
    patterns_path: Optional[str] = None
    inventory: Optional[TemplateInventory] = None
    overrides: List[PatternOverride] = []


def _config_asset_path(ctx: SaveContext, key: str) -> Optional[str]:
    """The KF path the `agent_assets` adapter stores a key under (same convention)."""
    team = ctx.identity.team_id
    instance = ctx.identity.agent_instance_id
    if not team or not instance:
        return None
    return f"teams/{team}/agents/{instance}/config/{key}"


def _bounded_analysis(content: bytes):
    """The offline analysis under the heavy-job slot, in a thread; errors as an envelope."""
    if len(content) > MAX_TEMPLATE_UPLOAD_BYTES:
        return AnalyzeResult(
            errors=[
                AnalysisError(
                    code=CODE_INVALID_UPLOAD,
                    message=f"The uploaded .pptx exceeds the {MAX_TEMPLATE_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
                )
            ]
        )
    return None


def _build_router() -> APIRouter:
    router = APIRouter(tags=["ppt_builder"])

    @router.post(
        "/analyze",
        response_model=AnalyzeResult,
        operation_id="analyzePptBuilderTemplate",
    )
    async def analyze(file: UploadFile = File(...)) -> AnalyzeResult:
        """Stateless analysis for the form's instant preview; stores nothing."""
        content = await file.read(MAX_TEMPLATE_UPLOAD_BYTES + 1)
        early = _bounded_analysis(content)
        if early is not None:
            return early
        if not acquire_heavy_job_slot():
            return AnalyzeResult(
                errors=[AnalysisError(code=CODE_SERVER_BUSY, message=_BUSY_MESSAGE)]
            )
        try:
            return await asyncio.to_thread(analyze_template, content)
        finally:
            release_heavy_job_slot()

    @router.post("/preview", operation_id="previewPptBuilderPatterns")
    async def preview(file: UploadFile = File(...)) -> Response:
        """One PDF page per pattern of the uploaded template, for the review thumbnails."""
        content = await file.read(MAX_TEMPLATE_UPLOAD_BYTES + 1)
        if len(content) > MAX_TEMPLATE_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail="The uploaded .pptx exceeds the size limit."
            )
        if not acquire_heavy_job_slot():
            raise HTTPException(status_code=503, detail=_BUSY_MESSAGE)
        try:
            result = await asyncio.to_thread(analyze_template, content)
            if result.inventory is None:
                raise HTTPException(
                    status_code=422,
                    detail="The uploaded file could not be read as a .pptx.",
                )
            deck = await asyncio.to_thread(
                build_patterns_deck, content, result.inventory
            )
        finally:
            release_heavy_job_slot()
        pdf = await convert_office_bytes_to_pdf(deck, suffix=".pptx")
        if pdf is None:
            raise HTTPException(
                status_code=503,
                detail="PDF conversion is not available on this server.",
            )
        return Response(content=pdf, media_type=_PDF_CONTENT_TYPE)

    @router.get(
        "/theme", response_model=AnalyzeResult, operation_id="getPptBuilderTheme"
    )
    async def theme() -> AnalyzeResult:
        """The built-in theme's inventory, shown when the agent has no template."""
        _, inventory = default_theme()
        return AnalyzeResult(inventory=inventory, summary=inventory.summary())

    @router.get("/theme/preview.pdf", operation_id="previewPptBuilderTheme")
    async def theme_preview() -> Response:
        pdf = await theme_preview_pdf()
        if pdf is None:
            raise HTTPException(
                status_code=503,
                detail="PDF conversion is not available on this server.",
            )
        return Response(content=pdf, media_type=_PDF_CONTENT_TYPE)

    return router


# The built-in theme is a process constant, so its thumbnails PDF is rendered
# once per pod (pod-local by nature) instead of one LibreOffice run per request.
_theme_pdf: Optional[bytes] = None
_theme_pdf_lock = asyncio.Lock()


async def theme_preview_pdf() -> Optional[bytes]:
    global _theme_pdf
    if _theme_pdf is not None:
        return _theme_pdf
    async with _theme_pdf_lock:
        if _theme_pdf is not None:
            return _theme_pdf
        template, inventory = default_theme()
        if not acquire_heavy_job_slot():
            raise HTTPException(status_code=503, detail=_BUSY_MESSAGE)
        try:
            deck = await asyncio.to_thread(build_patterns_deck, template, inventory)
        finally:
            release_heavy_job_slot()
        pdf = await convert_office_bytes_to_pdf(deck, suffix=".pptx")
        if pdf is not None:
            _theme_pdf = pdf
        return pdf


_BUILD_INSTRUCTIONS = (
    "PPT BUILDER: this agent builds PowerPoint presentations with the 'build_presentation' tool on a "
    "template its owner configured — NEVER ask the user to upload a template. When the user asks, in any "
    "wording or language, to produce, generate, create or prepare a PPT, PowerPoint, presentation, deck or "
    "slides, you MUST call 'build_presentation'; never answer with slide content in the chat instead. "
    "Work in two steps: (1) settle the outline with the user only if the request is too vague (audience, "
    "number of slides, key messages); otherwise (2) write the plan directly — one entry per slide with a "
    "pattern from the tool's catalogue and telegraphic content — and call the tool. Ground the content in "
    "the documents when the agent has document tools and the request refers to them. Keep every text "
    "SLIDE-READABLE: short titles, a few short bullets, never paragraphs; respect the limits the catalogue "
    "gives. If the tool reports truncations or substitutions, shorten or adjust and call it again. When the "
    "user asks for a change, regenerate the whole deck with the amended plan."
)


class _PptBuilderMiddleware(AgentMiddleware):
    """Carries the build tools and overlays the working rules on the system prompt."""

    def __init__(self, ctx: CapabilityContext[PptBuilderConfig, EmptyModel]) -> None:
        super().__init__()
        config = ctx.config
        assets = ctx.services.agent_assets

        if config.inventory is None:
            theme_bytes, theme_inventory = default_theme()
            effective, _ = apply_overrides(theme_inventory, config.overrides)

            async def load() -> bytes:
                return theme_bytes

        else:
            effective, _ = apply_overrides(config.inventory, config.overrides)
            template_key = config.template_key

            async def load() -> bytes:
                if assets is None:
                    raise RuntimeError(
                        "ppt_builder: RuntimeServices.agent_assets is not available on this execution path."
                    )
                return await assets.fetch(template_key)

        self.tools = build_builder_tools(ctx, load, effective)
        self._fragment = _BUILD_INSTRUCTIONS

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        base = request.system_prompt or ""
        merged = f"{base}\n\n{self._fragment}" if base else self._fragment
        request = request.override(system_message=SystemMessage(content=merged))
        return await handler(request)


class PptBuilderCapability(
    AgentCapability[PptBuilderConfig, PptBuilderConfig, EmptyModel]
):
    """Generate a presentation from a chat plan (see the module docstring)."""

    manifest = CapabilityManifest(
        id=PPT_BUILDER_CAPABILITY_ID,
        version="0.1.0",
        name="capability.ppt_builder.name",
        description="capability.ppt_builder.description",
        icon="co_present",
        config_fields=[
            # Both fields belong to the plugin's review widget (rendered once).
            FieldSpec(
                key="inventory",
                type="object",
                title="capability.ppt_builder.fields.inventory.title",
                description="capability.ppt_builder.fields.inventory.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
            FieldSpec(
                key="overrides",
                type="array",
                title="capability.ppt_builder.fields.overrides.title",
                description="capability.ppt_builder.fields.overrides.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
        ],
        assets=[
            AssetSlot(
                key=TEMPLATE_SLOT, accepted_types=[".pptx"], min_count=0, max_count=1
            )
        ],
        # The preview part is declared by ppt_filler (same package, one owner per kind).
        chat_parts=[],
        side_panels=[SidePanelSpec(widget="ppt_builder_preview_pane")],
        router=_build_router(),
        # The build tool's `pattern` enum is built per turn from the stored inventory.
        execution_models=("react",),
    )
    ConfigModel = PptBuilderConfig

    def __init__(self) -> None:
        super().__init__()
        # Warm the built-in theme at registration so its one-time build (tens
        # of milliseconds of python-pptx work) never lands inside a turn.
        default_theme()

    async def validate_config(
        self,
        config: PptBuilderConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> PptBuilderConfig:
        template_uploads = list(uploads.get(TEMPLATE_SLOT, ()))
        if not template_uploads:
            base = (
                config.inventory if config.inventory is not None else default_theme()[1]
            )
            kept, _ = prune_overrides(config.overrides, base)
            return config.model_copy(update={"overrides": kept})

        pptx_bytes = template_uploads[0].content
        early = _bounded_analysis(pptx_bytes)
        if early is not None:
            raise ValueError(early.errors[0].message)
        if not acquire_heavy_job_slot():
            raise RuntimeError(_BUSY_MESSAGE)
        try:
            result = await asyncio.to_thread(analyze_template, pptx_bytes)
            if result.inventory is None:
                raise ValueError(" | ".join(e.message for e in result.errors))
            inventory: TemplateInventory = result.inventory
            patterns_deck = await asyncio.to_thread(
                build_patterns_deck, pptx_bytes, inventory
            )
        finally:
            release_heavy_job_slot()

        assets = ctx.services.agent_assets
        if assets is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.agent_assets is not available on this save path; the template cannot be stored."
            )
        await assets.store(
            config.template_key,
            pptx_bytes,
            content_type=_PPTX_CONTENT_TYPE,
            filename=config.template_key,
        )

        # Thumbnails are best effort: a conversion failure never blocks the save.
        patterns_path: Optional[str] = None
        pdf = await convert_office_bytes_to_pdf(patterns_deck, suffix=".pptx")
        if pdf is not None:
            try:
                await assets.store(
                    config.patterns_key,
                    pdf,
                    content_type=_PDF_CONTENT_TYPE,
                    filename=config.patterns_key,
                )
                patterns_path = _config_asset_path(ctx, config.patterns_key)
            except Exception as exc:  # noqa: BLE001 - thumbnails only
                logger.warning("[PPTBUILD] patterns preview store failed: %s", exc)

        kept, dropped = prune_overrides(config.overrides, inventory)
        if dropped:
            logger.info("[PPTBUILD] overrides dropped after re-upload: %s", dropped)
        return config.model_copy(
            update={
                "inventory": inventory,
                "overrides": kept,
                "patterns_path": patterns_path,
            }
        )

    def middleware(
        self, ctx: CapabilityContext[PptBuilderConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_PptBuilderMiddleware(ctx)]
