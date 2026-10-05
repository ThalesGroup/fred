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
template, or on the built-in template when the agent has none.

The save never waits on the analysis: it stores the template, records a pending
analysis row and returns; ``analysis_job`` runs it in the background (design.md
D4) and ``readiness`` keeps the agent unavailable until it succeeds (D5). The
preview chat part and side pane are ``ppt_filler``'s (one owner per kind).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetSlot,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    CapabilityReadiness,
    EmptyModel,
    SaveContext,
    SidePanelSpec,
    UploadedFile,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import (
    CapabilityTeamAuthorizer,
    capability_team_authorizer,
)
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool, StructuredTool
from pptx import Presentation
from pydantic import BaseModel

from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder.analysis import (
    ANALYSIS_VERSION,
)
from fred_capability_ppt_filler.builder.analysis_job import (
    AnalysisRecord,
    AnalysisRow,
    AnalysisStatusResponse,
    analysis_readiness,
    get_analysis_store,
    labelling_key,
    ready_inventory,
    restart_from_stored,
    spawn_analysis,
    status_response,
)
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.models import (
    AnalysisError,
    AnalyzeResult,
    PatternOverride,
)
from fred_capability_ppt_filler.builder.overrides import (
    apply_overrides,
    prune_overrides,
)
from fred_capability_ppt_filler.builder.preview import build_patterns_deck
from fred_capability_ppt_filler.builder.tools import (
    BUILD_TOOL_NAME,
    PPT_BUILDER_CAPABILITY_ID,
    _error,
    build_builder_tools,
    build_list_images_tool,
)
from fred_capability_ppt_filler.capability import (
    CODE_INVALID_UPLOAD,
    MAX_TEMPLATE_UPLOAD_BYTES,
    TEMPLATE_SLOT,
)
from fred_capability_ppt_filler.concurrency import (
    acquire_heavy_job_slot,
    release_heavy_job_slot,
)

logger = logging.getLogger(__name__)

PPT_BUILDER_TEMPLATE_KEY = "ppt_builder_template.pptx"

_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
_PDF_CONTENT_TYPE = "application/pdf"
_BUSY_MESSAGE = "The server is busy analysing other PowerPoint templates right now. Please try again in a moment."
_ANALYSING_MESSAGE = (
    "The presentation template is still being analysed, so no deck can be built yet. Tell the "
    "user to try again in a minute."
)
_NOT_READY_MESSAGE = (
    "The presentation template analysis did not succeed, so no deck can be built. Tell the user "
    "that the agent's owner must re-run the analysis in the agent settings."
)


class PptBuilderConfig(BaseModel):
    """Stored config (ConfigModel == StoredConfigModel). ``template_sha256``
    names the analysed template; ``None`` means the built-in template. The
    analysis itself lives in ``cap_ppt_builder_analysis``."""

    template_key: str = PPT_BUILDER_TEMPLATE_KEY
    template_sha256: Optional[str] = None
    use_vision: bool = True
    labelling_model: Optional[str] = None
    overrides: List[PatternOverride] = []

    def labelling_key(self) -> str:
        return labelling_key(self.use_vision, self.labelling_model)


def _bounded_analysis(content: bytes):
    """The size gate shared by the stateless routes; errors as an envelope."""
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


def _check_readable(content: bytes) -> None:
    """Fail the save on an unreadable .pptx (cheap: opening, not analysing)."""
    try:
        Presentation(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a template error
        raise ValueError(
            f"The uploaded file could not be read as a .pptx: {exc}"
        ) from exc


async def _authorised_record(
    instance_id: str, authorizer: CapabilityTeamAuthorizer
) -> AnalysisRecord:
    record = await get_analysis_store().get(instance_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No template analysis.")
    await authorizer.require_agent_editor(record.team_id)
    return record


def _build_router() -> APIRouter:
    router = APIRouter(tags=["ppt_builder"])

    @router.get(
        "/builtin", response_model=AnalyzeResult, operation_id="getPptBuilderBuiltin"
    )
    async def builtin() -> AnalyzeResult:
        """The built-in template's inventory, shown when the agent has no template."""
        _, inventory = builtin_template()
        return AnalyzeResult(inventory=inventory, summary=inventory.summary())

    @router.get("/builtin/patterns.pdf", operation_id="getPptBuilderBuiltinPatterns")
    async def builtin_patterns() -> Response:
        pdf = await builtin_patterns_pdf()
        if pdf is None:
            raise HTTPException(
                status_code=503,
                detail="PDF conversion is not available on this server.",
            )
        return Response(content=pdf, media_type=_PDF_CONTENT_TYPE)

    @router.get(
        "/analysis/{instance_id}",
        response_model=AnalysisStatusResponse,
        operation_id="getPptBuilderAnalysis",
    )
    async def analysis_status(
        instance_id: str,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> AnalysisStatusResponse:
        """Status, summary and inventory of the instance's template analysis."""
        return status_response(await _authorised_record(instance_id, authorizer))

    @router.get(
        "/analysis/{instance_id}/patterns.pdf",
        operation_id="getPptBuilderAnalysisPatterns",
    )
    async def analysis_patterns(
        instance_id: str,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> Response:
        """One PDF page per pattern of the analysed template (the thumbnails)."""
        await _authorised_record(instance_id, authorizer)
        pdf = await get_analysis_store().patterns_pdf(instance_id)
        if pdf is None:
            raise HTTPException(status_code=404, detail="No thumbnails.")
        return Response(content=pdf, media_type=_PDF_CONTENT_TYPE)

    @router.post(
        "/analysis/{instance_id}/rerun",
        response_model=AnalysisStatusResponse,
        operation_id="rerunPptBuilderAnalysis",
    )
    async def analysis_rerun(
        instance_id: str,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> AnalysisStatusResponse:
        """Re-run a failed, interrupted or outdated analysis from the stored template."""
        record = await _authorised_record(instance_id, authorizer)
        status = status_response(record).status
        if status in ("pending", "running"):
            raise HTTPException(status_code=409, detail="The analysis is running.")
        if status == "succeeded" and record.analysis_version >= ANALYSIS_VERSION:
            raise HTTPException(status_code=409, detail="The analysis succeeded.")
        store = get_analysis_store()
        await restart_from_stored(store, record)
        refreshed = await store.get(instance_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="No template analysis.")
        return status_response(refreshed)

    return router


# The built-in template is a process constant, so its patterns PDF is rendered
# once per pod (pod-local by nature) instead of one LibreOffice run per request.
_builtin_pdf: Optional[bytes] = None
_builtin_pdf_lock = asyncio.Lock()


async def builtin_patterns_pdf() -> Optional[bytes]:
    global _builtin_pdf
    if _builtin_pdf is not None:
        return _builtin_pdf
    async with _builtin_pdf_lock:
        if _builtin_pdf is not None:
            return _builtin_pdf
        template, inventory = builtin_template()
        if not acquire_heavy_job_slot():
            raise HTTPException(status_code=503, detail=_BUSY_MESSAGE)
        try:
            deck = await asyncio.to_thread(build_patterns_deck, template, inventory)
        finally:
            release_heavy_job_slot()
        pdf = await convert_office_bytes_to_pdf(deck, suffix=".pptx")
        if pdf is not None:
            _builtin_pdf = pdf
        return pdf


_BUILD_INSTRUCTIONS = (
    "PPT BUILDER: this agent builds PowerPoint presentations with the 'build_presentation' tool on a "
    "template its owner configured — NEVER ask the user to upload a template. When the user asks, in any "
    "wording or language, to produce, generate, create or prepare a PPT, PowerPoint, presentation, deck or "
    "slides, you MUST call 'build_presentation'; never answer with slide content in the chat instead. "
    "Work in two steps: (1) settle the outline with the user only if the request is too vague (audience, "
    "number of slides, key messages); otherwise (2) write the plan directly — one entry per slide with its "
    "content, then optionally its kind — and call the tool. Ground the content in "
    "the documents when the agent has document tools and the request refers to them. Keep every text "
    "SLIDE-READABLE: short titles, a few short bullets, never paragraphs; respect the limits the catalogue "
    "gives. If the tool returns needs_revision, apply one option per listed slide and call again with the "
    "WHOLE deck; if it reports cuts that matter, fix them the same way. When the "
    "user asks for a change, regenerate the whole deck with the amended plan."
)


def _plain(value: Any) -> Any:
    """Validated tool arguments back to JSON shapes for another schema."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


class _PptBuilderMiddleware(AgentMiddleware):
    """Carries the build tools and overlays the working rules on the system prompt.

    With a template, the analysis is read on the first model call (one DB read
    per template per pod, then cached); the registered build tool delegates to
    the template's tool and refuses while the analysis has not succeeded."""

    def __init__(self, ctx: CapabilityContext[PptBuilderConfig, EmptyModel]) -> None:
        super().__init__()
        self._ctx = ctx
        self._fragment = _BUILD_INSTRUCTIONS
        self._resolved: Optional[List[BaseTool]] = None
        self._refusal = _ANALYSING_MESSAGE
        config = ctx.config
        identity = ctx.identity
        self._sha = config.template_sha256
        self._instance = identity.agent_instance_id
        self._key = config.labelling_key()

        if self._sha is None:
            builtin_bytes, builtin_inventory = builtin_template()

            async def load_builtin() -> bytes:
                return builtin_bytes

            effective, _ = apply_overrides(builtin_inventory, config.overrides)
            self.tools = build_builder_tools(ctx, load_builtin, effective)
            self._resolved = self.tools
            return
        cached = (
            analysis_job.cached_inventory(self._instance, self._sha, self._key)
            if self._instance
            else None
        )
        if cached is not None:  # the usual turn: no DB read, no indirection
            effective, _ = apply_overrides(cached, config.overrides)
            self.tools = build_builder_tools(ctx, self._load_template, effective)
            self._resolved = self.tools
            return

        # Same schema as the template's tool (validation accepts any kind).
        generic = build_builder_tools(ctx, self._load_template, builtin_template()[1])[
            0
        ]
        deferred = StructuredTool.from_function(
            coroutine=self._deferred_build,
            name=BUILD_TOOL_NAME,
            description=_ANALYSING_MESSAGE,
            args_schema=generic.args_schema,
            response_format="content_and_artifact",
        )
        self.tools = [deferred, build_list_images_tool(ctx)]

    async def _load_template(self) -> bytes:
        assets = self._ctx.services.agent_assets
        if assets is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.agent_assets is not available on this execution path."
            )
        return await assets.fetch(self._ctx.config.template_key)

    async def _resolve(self) -> Optional[List[BaseTool]]:
        if self._resolved is not None or self._sha is None:
            return self._resolved
        if not self._instance:
            return None
        store = get_analysis_store()
        try:
            inventory = await ready_inventory(
                store, self._instance, self._sha, self._key
            )
            if inventory is None:
                verdict = await analysis_readiness(
                    store, self._instance, self._sha, self._key
                )
                if verdict.state == "failed":
                    self._refusal = _NOT_READY_MESSAGE
                return None
        except Exception:  # the turn goes on; the tool refuses
            logger.warning("Template analysis unreadable", exc_info=True)
            return None
        effective, _ = apply_overrides(inventory, self._ctx.config.overrides)
        self._resolved = build_builder_tools(self._ctx, self._load_template, effective)
        return self._resolved

    async def _deferred_build(self, **kwargs: object) -> Any:
        tools = await self._resolve()
        if tools is None:
            return _error(self._refusal)
        coroutine = getattr(tools[0], "coroutine", None)
        if coroutine is None:  # pragma: no cover - build_builder_tools contract
            return _error(_NOT_READY_MESSAGE)
        return await coroutine(**{k: _plain(v) for k, v in kwargs.items()})

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        base = request.system_prompt or ""
        merged = f"{base}\n\n{self._fragment}" if base else self._fragment
        update: dict[str, Any] = {"system_message": SystemMessage(content=merged)}
        tools = await self._resolve()
        if tools is not None and tools is not self.tools:
            # Same name, so the model sees the template's catalogue and enum
            # while execution stays with the registered tool.
            real = tools[0]
            update["tools"] = [
                real if getattr(t, "name", None) == BUILD_TOOL_NAME else t
                for t in request.tools
            ]
        return await handler(request.override(**update))


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
            # All four fields belong to the plugin's widget (rendered once): the
            # vision toggle depends on the team's models, which a generic field cannot know.
            FieldSpec(
                key="template_sha256",
                type="string",
                title="capability.ppt_builder.fields.template.title",
                description="capability.ppt_builder.fields.template.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
            FieldSpec(
                key="overrides",
                type="array",
                title="capability.ppt_builder.fields.overrides.title",
                description="capability.ppt_builder.fields.overrides.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
            FieldSpec(
                key="use_vision",
                type="boolean",
                default=True,
                title="capability.ppt_builder.fields.use_vision.title",
                description="capability.ppt_builder.fields.use_vision.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
            FieldSpec(
                key="labelling_model",
                type="string",
                title="capability.ppt_builder.fields.labelling_model.title",
                description="capability.ppt_builder.fields.labelling_model.description",
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
        side_panels=[SidePanelSpec(widget="ppt_preview_pane")],
        router=_build_router(),
        tables=[AnalysisRow],
        # The build tool's description and `kind` enum come from the analysis.
        execution_models=("react",),
    )
    ConfigModel = PptBuilderConfig

    def __init__(self) -> None:
        super().__init__()
        # Load the built-in template at registration so its one-time read never
        # lands inside a turn.
        builtin_template()

    @classmethod
    def migrations_location(cls) -> str:
        """Applied under `cap_ppt_builder_alembic_version` by `python -m fred_runtime migrate`."""
        return str(Path(__file__).resolve().parent / "ppt_builder_migrations")

    async def validate_config(
        self,
        config: PptBuilderConfig,
        uploads: Mapping[str, list[UploadedFile]],
        ctx: SaveContext,
    ) -> PptBuilderConfig:
        """Store the template and start its analysis in the background; never
        waits for it. A re-validation without an instance has no side effect."""
        template_uploads = list(uploads.get(TEMPLATE_SLOT, ()))
        if template_uploads:
            return await self._accept_upload(config, template_uploads[0].content, ctx)
        if config.template_sha256 is None:
            kept, _ = prune_overrides(config.overrides, builtin_template()[1])
            return config.model_copy(update={"overrides": kept})
        instance = ctx.identity.agent_instance_id
        if not instance or not ctx.identity.team_id:
            return config

        store = get_analysis_store()
        record = await store.get(instance)
        key = config.labelling_key()
        if record is None or record.template_sha256 != config.template_sha256:
            await self._start_from_assets(config, ctx)
        elif self._needs_rerun(record, key):
            analysis_job.remember_port(instance, ctx.services.capability_model)
            await restart_from_stored(store, record, labelling_key=key)
        else:
            inventory = (
                record.inventory()
                if record.matches(config.template_sha256, key)
                else None
            )
            if inventory is not None:
                kept, dropped = prune_overrides(config.overrides, inventory)
                if dropped:
                    logger.info("Overrides dropped after re-analysis: %s", dropped)
                return config.model_copy(update={"overrides": kept})
        return config

    @staticmethod
    def _needs_rerun(record: AnalysisRecord, key: str) -> bool:
        if record.labelling_key != key or record.status == "failed":
            return True
        if record.status == "succeeded":
            return record.analysis_version < ANALYSIS_VERSION
        return record.interrupted(analysis_job._utcnow())

    async def _accept_upload(
        self, config: PptBuilderConfig, content: bytes, ctx: SaveContext
    ) -> PptBuilderConfig:
        early = _bounded_analysis(content)
        if early is not None:
            raise ValueError(early.errors[0].message)
        if not acquire_heavy_job_slot():
            raise RuntimeError(_BUSY_MESSAGE)
        try:
            await asyncio.to_thread(_check_readable, content)
        finally:
            release_heavy_job_slot()
        assets = ctx.services.agent_assets
        if assets is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.agent_assets is not available on this save path; the template cannot be stored."
            )
        await assets.store(
            config.template_key,
            content,
            content_type=_PPTX_CONTENT_TYPE,
            filename=config.template_key,
        )
        sha = await self._launch(config, content, ctx)
        return config.model_copy(update={"template_sha256": sha})

    async def _start_from_assets(
        self, config: PptBuilderConfig, ctx: SaveContext
    ) -> None:
        assets = ctx.services.agent_assets
        if assets is None:
            raise RuntimeError(
                "ppt_builder: RuntimeServices.agent_assets is not available on this save path."
            )
        try:
            content = await assets.fetch(config.template_key)
        except Exception as exc:  # noqa: BLE001 - the author can upload it again
            raise ValueError(
                "The stored template could not be read; upload it again."
            ) from exc
        await self._launch(config, content, ctx)

    @staticmethod
    async def _launch(
        config: PptBuilderConfig, content: bytes, ctx: SaveContext
    ) -> str:
        instance = ctx.identity.agent_instance_id
        team = ctx.identity.team_id
        if not instance or not team:
            raise RuntimeError(
                "ppt_builder: a template can only be analysed for a saved agent of a team."
            )
        sha = hashlib.sha256(content).hexdigest()
        key = config.labelling_key()
        store = get_analysis_store()
        job_id = await store.start(
            instance_id=instance,
            team_id=team,
            saved_by=ctx.identity.user_id,
            template_sha256=sha,
            labelling_key=key,
            template=content,
        )
        analysis_job.remember_port(instance, ctx.services.capability_model)
        spawn_analysis(store, instance, job_id, content, key)
        return sha

    async def readiness(
        self, stored: PptBuilderConfig, identity: CapabilityIdentity
    ) -> CapabilityReadiness:
        """Ready on the built-in template or once the template analysis succeeded."""
        instance = identity.agent_instance_id
        if stored.template_sha256 is None or not instance:
            return CapabilityReadiness.ready()
        return await analysis_readiness(
            get_analysis_store(),
            instance,
            stored.template_sha256,
            stored.labelling_key(),
        )

    def middleware(
        self, ctx: CapabilityContext[PptBuilderConfig, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_PptBuilderMiddleware(ctx)]
