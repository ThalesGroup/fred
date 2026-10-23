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
analysis row and returns; ``analysis_job`` runs it in the background and
``readiness`` keeps the agent unavailable until it succeeds. The preview chat
part and side pane are ``ppt_filler``'s (one owner per kind).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, List, Optional, get_args

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fred_core import convert_office_bytes_to_pdf
from fred_sdk.contracts.capability import (
    AgentCapability,
    AssetKey,
    AssetSlot,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    CapabilityReadiness,
    EmptyModel,
    Public,
    SaveContext,
    SidePanelSpec,
    UploadedFile,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import (
    CapabilityModelPort,
    CapabilityModelUnavailableError,
    CapabilityTeamAuthorizer,
    capability_platform_model,
    capability_team_authorizer,
)
from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, model_validator

from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder.analysis_job import (
    BUILTIN_ID,
    PLATFORM_ID,
    PLATFORM_NEXT_ID,
    AnalysisOwnershipError,
    AnalysisRecord,
    AnalysisRow,
    AnalysisStatusResponse,
    PlatformDefault,
    analysed_template,
    analysis_readiness,
    dump_overrides,
    get_analysis_store,
    labelling_key,
    parse_labelling_key,
    ready_inventory,
    recover_interrupted,
    refresh_outdated,
    restart_from_stored,
    spawn_analysis,
    status_response,
)
from fred_capability_ppt_filler.builder.assign import VarietyCheck
from fred_capability_ppt_filler.builder.builtin import builtin_template, sha256_of
from fred_capability_ppt_filler.builder.deck_plans import DeckPlanRow
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
    _answer,
    _error,
    answer_closed,
    build_builder_tools,
    build_list_images_tool,
    round_refusal,
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
from fred_capability_ppt_filler.pptx_archive import (
    UnsafeArchiveError,
    open_presentation,
    sanitize_template,
    unreadable_message,
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
    "that the agent's owner must save the agent again in its settings to re-run the analysis."
)


class PptBuilderConfig(BaseModel):
    """Stored config (ConfigModel == StoredConfigModel). ``template_sha256``
    names the analysed template; ``None`` means the built-in template. The
    analysis itself lives in ``cap_ppt_builder_analysis``."""

    # Set only for an uploaded template, so a copy re-submits that file alone.
    template_key: Annotated[Optional[str], AssetKey(TEMPLATE_SLOT)] = None
    template_sha256: Optional[str] = None
    use_vision: bool = True
    # A catalogue profile: a team that may not use it falls back to rules.
    labelling_model: Public[Optional[str]] = None
    overrides: List[PatternOverride] = []
    # Read by the build tool each turn, never by the analysis: no re-run.
    variety_check: VarietyCheck = "template_slide"
    variety_max_uses: int = Field(default=2, ge=1, le=5)
    # On: the first build of a conversation returns the outline for the user.
    validate_plan: bool = False

    @model_validator(mode="after")
    def _template_key_follows_sha(self) -> "PptBuilderConfig":
        self.template_key = PPT_BUILDER_TEMPLATE_KEY if self.template_sha256 else None
        return self

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


_STORE_UNAVAILABLE = (
    "The template cannot be stored right now. Try again later; if it keeps "
    "failing, contact your administrator."
)


def _require_agent_instance(instance_id: Optional[str]) -> None:
    """A team save names a real agent: an instance id is a UUID, so the
    platform rows (``__platform__``…) are never reachable from it."""
    if not instance_id:
        return
    try:
        canonical = str(uuid.UUID(instance_id)) == instance_id
    except ValueError:
        canonical = False
    if not canonical:
        logger.warning("[PPTBUILD] template save refused for a non-agent id")
        raise ValueError("This save does not name a saved agent.")


def _require_own_row(record: Optional[AnalysisRecord], team_id: Optional[str]) -> None:
    if record is not None and record.team_id != team_id:
        logger.warning("[PPTBUILD] template save refused: the row is another team's")
        raise AnalysisOwnershipError("This agent's template belongs to another team.")


def _check_readable(content: bytes) -> bytes:
    """The upload as stored: sanitised, and opened to fail the save on an
    unreadable .pptx (cheap: opening, not analysing)."""
    try:
        content = sanitize_template(content)
        open_presentation(content)
    except UnsafeArchiveError as exc:
        raise ValueError(f"The uploaded file could not be read: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a template error
        logger.info("[PPTBUILD] unreadable template upload: %s", type(exc).__name__)
        raise ValueError(unreadable_message(content)) from exc
    return content


async def _authorised_record(
    instance_id: str, authorizer: CapabilityTeamAuthorizer
) -> AnalysisRecord:
    # The platform rows have their own routes: their team id is no team to check.
    record = (
        None
        if instance_id in (PLATFORM_ID, PLATFORM_NEXT_ID, BUILTIN_ID)
        else await get_analysis_store().get(instance_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No template analysis.")
    await authorizer.require_agent_editor(record.team_id)
    return record


class PlatformTemplateResponse(BaseModel):
    """The platform default template. ``analysis`` is the template in effect,
    None while it is the Fred template; ``replacement`` is one being analysed
    or failed, which agents do not use until it succeeds."""

    analysis: Optional[AnalysisStatusResponse] = None
    template_filename: Optional[str] = None
    # The manager's pattern edits of the template in effect (the Fred template's
    # while ``analysis`` is None), applied for every agent on it.
    overrides: List[PatternOverride] = []
    replacement: Optional[AnalysisStatusResponse] = None
    replacement_filename: Optional[str] = None
    # The replacement's choice, else the current one's. None: the platform's default model.
    use_vision: bool = True
    vision_profile_id: Optional[str] = None


class PlatformOverridesRequest(BaseModel):
    overrides: List[PatternOverride] = []


class PlatformAnalysisRequest(BaseModel):
    """The vision choice a platform analysis runs with."""

    use_vision: bool = True
    vision_profile_id: Optional[str] = None


async def _platform_response(*, recover: bool = False) -> PlatformTemplateResponse:
    store = get_analysis_store()
    current = await store.get(PLATFORM_ID)
    replacement = await store.get(PLATFORM_NEXT_ID, with_inventory=False)
    if (
        recover
        and replacement is not None
        and replacement.interrupted(analysis_job._utcnow())
        and await recover_interrupted(store, PLATFORM_NEXT_ID)
    ):
        replacement = await store.get(PLATFORM_NEXT_ID, with_inventory=False)
    overrides = current.overrides() if current else await _builtin_overrides()
    latest = replacement or current
    if latest is None:
        return PlatformTemplateResponse(overrides=overrides)
    use_vision, profile_id = parse_labelling_key(latest.labelling_key)
    return PlatformTemplateResponse(
        analysis=status_response(current) if current else None,
        template_filename=current.template_filename if current else None,
        overrides=overrides,
        replacement=status_response(replacement) if replacement else None,
        replacement_filename=replacement.template_filename if replacement else None,
        use_vision=use_vision,
        vision_profile_id=profile_id,
    )


async def _builtin_overrides() -> List[PatternOverride]:
    """The manager's edits of the Fred template, pruned against the shipped one."""
    record = await get_analysis_store().get(BUILTIN_ID, with_inventory=False)
    if record is None:
        return []
    kept, _ = prune_overrides(record.overrides(), builtin_template()[1])
    return kept


async def _platform_labelling_key(
    port: CapabilityModelPort, use_vision: bool, profile_id: Optional[str]
) -> str:
    """422 for a vision model the platform drawer would not offer."""
    if use_vision and profile_id:
        try:
            await port.require_vision_profile(profile_id)
        except CapabilityModelUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return labelling_key(use_vision, profile_id or None)


def _remember_platform_port(port: CapabilityModelPort) -> None:
    # Both rows: a replacement's job, and the outdated refresh of the current one.
    analysis_job.remember_port(PLATFORM_NEXT_ID, port)
    analysis_job.remember_port(PLATFORM_ID, port)


async def _readable_upload(file: UploadFile) -> bytes:
    """The agent save's gates: size, then a cheap readability check."""
    content = await file.read(MAX_TEMPLATE_UPLOAD_BYTES + 1)
    early = _bounded_analysis(content)
    if early is not None:
        raise HTTPException(status_code=413, detail=early.errors[0].message)
    if not acquire_heavy_job_slot():
        raise HTTPException(status_code=503, detail=_BUSY_MESSAGE)
    try:
        content = await asyncio.to_thread(_check_readable, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        release_heavy_job_slot()
    return content


async def start_analysis(
    *,
    instance_id: str,
    team_id: str,
    saved_by: Optional[str],
    content: bytes,
    key: str,
    port: Optional[CapabilityModelPort],
    filename: Optional[str] = None,
) -> str:
    """Store the template as a pending analysis and run it in the background."""
    sha = hashlib.sha256(content).hexdigest()
    store = get_analysis_store()
    current = await store.get(instance_id, with_inventory=False)
    _require_own_row(current, team_id)
    if (
        current is not None
        and current.status == "succeeded"
        and not current.outdated()
        and (current.template_sha256, current.labelling_key) == (sha, key)
    ):
        return sha  # the same file again: its analysis stands
    job_id = await store.start(
        instance_id=instance_id,
        team_id=team_id,
        saved_by=saved_by,
        template_sha256=sha,
        labelling_key=key,
        template=content,
        template_filename=filename,
    )
    analysis_job.remember_port(instance_id, port)
    spawn_analysis(store, instance_id, job_id, content, key)
    return sha


def _build_router() -> APIRouter:
    router = APIRouter(tags=["ppt_builder"])

    @router.get(
        "/platform",
        response_model=PlatformTemplateResponse,
        operation_id="getPptBuilderPlatform",
    )
    async def platform() -> PlatformTemplateResponse:
        """The platform default template and its analysis (any signed-in user)."""
        return await _platform_response(recover=True)

    @router.get("/platform/patterns.pdf", operation_id="getPptBuilderPlatformPatterns")
    async def platform_patterns() -> Response:
        pdf = await get_analysis_store().patterns_pdf(PLATFORM_ID)
        if pdf is None:
            raise HTTPException(status_code=404, detail="No thumbnails.")
        return Response(content=pdf, media_type=_PDF_CONTENT_TYPE)

    @router.put(
        "/platform/template",
        response_model=PlatformTemplateResponse,
        operation_id="putPptBuilderPlatformTemplate",
    )
    async def put_platform_template(
        file: UploadFile = File(...),
        use_vision: bool = Form(True),
        vision_profile_id: Optional[str] = Form(None),
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
        port: CapabilityModelPort = Depends(capability_platform_model),
    ) -> PlatformTemplateResponse:
        """Replace the platform default template; the current one stays in use
        until the replacement's analysis succeeds."""
        await authorizer.require_capability_manager()
        key = await _platform_labelling_key(port, use_vision, vision_profile_id)
        content = await _readable_upload(file)
        store = get_analysis_store()
        current = await store.get(PLATFORM_ID, with_inventory=False)
        if (
            current is not None
            and not current.outdated()
            and current.template_sha256 == hashlib.sha256(content).hexdigest()
            and current.labelling_key == key
        ):
            await store.delete(PLATFORM_NEXT_ID)  # the same file: its analysis stands
            return await _platform_response()
        _remember_platform_port(port)
        await start_analysis(
            instance_id=PLATFORM_NEXT_ID,
            team_id=PLATFORM_ID,
            saved_by=None,
            content=content,
            key=key,
            port=port,
            filename=(file.filename or "")[:255] or None,
        )
        return await _platform_response()

    @router.post(
        "/platform/analysis",
        response_model=PlatformTemplateResponse,
        operation_id="rerunPptBuilderPlatformAnalysis",
    )
    async def rerun_platform_analysis(
        body: PlatformAnalysisRequest,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
        port: CapabilityModelPort = Depends(capability_platform_model),
    ) -> PlatformTemplateResponse:
        """Analyse the platform template again, with this vision choice: the
        failed replacement, else the current template, which stays in use."""
        await authorizer.require_capability_manager()
        key = await _platform_labelling_key(
            port, body.use_vision, body.vision_profile_id
        )
        store = get_analysis_store()
        _remember_platform_port(port)
        replacement = await store.get(PLATFORM_NEXT_ID, with_inventory=False)
        if replacement is not None:
            await restart_from_stored(store, replacement, labelling_key=key)
            return await _platform_response()
        current = await store.get(PLATFORM_ID, with_inventory=False)
        content = await store.template(PLATFORM_ID) if current else None
        if current is None or content is None:
            raise HTTPException(status_code=404, detail="No platform template.")
        job_id = await store.start(
            instance_id=PLATFORM_NEXT_ID,
            team_id=PLATFORM_ID,
            saved_by=None,
            template_sha256=current.template_sha256,
            labelling_key=key,
            template=content,
            template_filename=current.template_filename,
        )
        spawn_analysis(store, PLATFORM_NEXT_ID, job_id, content, key)
        return await _platform_response()

    @router.put(
        "/platform/overrides",
        response_model=PlatformTemplateResponse,
        operation_id="putPptBuilderPlatformOverrides",
    )
    async def put_platform_overrides(
        body: PlatformOverridesRequest,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> PlatformTemplateResponse:
        """The manager's pattern edits of the template in effect: the platform
        template, else the Fred template."""
        await authorizer.require_capability_manager()
        store = get_analysis_store()
        current = await store.get(PLATFORM_ID)
        if current is None:
            content, builtin = builtin_template()
            kept, _ = prune_overrides(body.overrides, builtin)
            await store.set_builtin_overrides(sha256_of(content), dump_overrides(kept))
            analysis_job.forget_platform_default()
            return await _platform_response()
        inventory = current.inventory()
        if inventory is None:
            raise HTTPException(status_code=404, detail="No platform template.")
        kept, _ = prune_overrides(body.overrides, inventory)
        if not await store.set_overrides(PLATFORM_ID, dump_overrides(kept)):
            raise HTTPException(status_code=404, detail="No platform template.")
        analysis_job.forget_platform_default()
        return await _platform_response()

    @router.delete(
        "/platform/template",
        response_model=PlatformTemplateResponse,
        operation_id="deletePptBuilderPlatformTemplate",
    )
    async def reset_platform_template(
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> PlatformTemplateResponse:
        """Back to the Fred template, which itself cannot be removed, without
        the manager's edits of it."""
        await authorizer.require_capability_manager()
        store = get_analysis_store()
        await store.delete(PLATFORM_NEXT_ID)
        await store.delete(PLATFORM_ID)
        await store.delete(BUILTIN_ID)
        analysis_job.forget_inventories(PLATFORM_ID)
        return PlatformTemplateResponse()

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


# Where the deck's look comes from: the tool cannot switch template, so a
# request for another one is answered with where it is set.
_TEMPLATES = {
    True: "the platform's default template (this agent has no template of its own)",
    False: "the template uploaded in this agent's settings",
}

_BUILD_INSTRUCTIONS = (
    "PPT BUILDER: this agent builds PowerPoint presentations with the 'build_presentation' tool on "
    "{template}; it cannot switch template: an editor of the agent uploads another in its settings, "
    "never in the chat. When the user asks, in any "
    "wording or language, to produce, generate, create or prepare a PPT, PowerPoint, presentation, deck or "
    "slides, you MUST call 'build_presentation'; never answer with slide content in the chat instead. "
    "Build directly: write the plan — one entry per slide with its takeaway, its content, then optionally its kind — and "
    "call the tool in this answer, choosing the audience and length yourself when the user does not say. "
    "{outline} Ground the content in "
    "the documents when the agent has document tools and the request refers to them. Keep every text "
    "SLIDE-READABLE: short titles, a few short bullets, never paragraphs, within the catalogue's room. "
    "Tell a story: decide the deck's main message, then each content slide's "
    "`takeaway` (what the audience concludes, as a sentence) before its content. Let the takeaway design "
    "the slide: the kind that shows it (a comparison → a chart; one striking number → a figures slide; a "
    "trend → a line), only the content that supports it, and the emphasis that proves it (chart.highlight, "
    "chart.sort). Then write its title: that conclusion as a short sentence (a claim, not a topic); "
    "leave titles out only when the user asked. Keep every figure, name and date from the documents or the "
    "user exact when rewording, and say where in `source` ('user' only for what the user wrote; none for "
    "general knowledge). "
    "Never invent one: when the user asks for concrete figures they did not give, ask for them, unless they "
    "asked for illustrative data. If the tool returns needs_revision, nothing was built yet: your very "
    "next message MUST be a new 'build_presentation' call with the fixes applied as its result says, "
    "never a final answer, unless the user must decide something. "
    "Make it as a real tool call: never write the call, its JSON or the planned fixes in your reply text. "
    "A delivered deck or a proposed plan ends the answer: no tool can be called after it, so tell "
    "the user what its result says, cuts and notes included. "
    "When the user asks to change the deck, do only that (propose any "
    "other slide or content instead), with `changes` for the slides concerned; the whole deck in `slides` "
    "only for a new deck or a rewrite of most slides. Never drop or replace a slide to keep an "
    "earlier slide count unless the user asks for a count. When the request does not say which slide, act on "
    "the one slide it can mean ('this table' with one table in the deck); ask only when several "
    "could match. Say a deck was built or changed only when build_presentation delivered it in this "
    "answer; describe only what its result lists, and say so when a request needed no change or could "
    "not be applied."
)


# With the plan gate the tool shows the outline: one written in the chat
# would be validated twice.
_OUTLINE = {
    False: "Ask the user to validate an outline first only when they asked for it, or when the "
    "request does not say what the presentation is about.",
    True: "Ask first only when the request does not say what the presentation is about; never "
    "write an outline in the chat: the tool shows one to the user before the first deck. Building "
    "directly means calling the tool: when it proposes a plan, your answer shows that outline, "
    "then ends; the user answers first, so never call the tool again in that answer.",
}


def build_instructions(builtin: bool, validate_plan: bool = False) -> str:
    """The working rules overlaid on the system prompt, naming the template."""
    return _BUILD_INSTRUCTIONS.format(
        template=_TEMPLATES[builtin], outline=_OUTLINE[validate_plan]
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
    the template's tool and refuses while the analysis has not succeeded.
    Without one, the platform default comes from the pod's snapshot."""

    def __init__(self, ctx: CapabilityContext[PptBuilderConfig, EmptyModel]) -> None:
        super().__init__()
        self._ctx = ctx
        self._fragment = build_instructions(
            ctx.config.template_sha256 is None, ctx.config.validate_plan
        )
        self._resolved: Optional[List[BaseTool]] = None
        self._refusal = _ANALYSING_MESSAGE
        # The last model call's messages: the build tool reads whether a deck was delivered.
        self._history: Sequence[BaseMessage] = ()
        config = ctx.config
        identity = ctx.identity
        self._sha = config.template_sha256
        self._instance = identity.agent_instance_id
        self._key = config.labelling_key()

        if self._sha is None:
            known, platform = analysis_job.platform_snapshot()
            if known:  # the usual turn: no DB read
                self.tools = self._default_tools(platform)
                self._resolved = self.tools
                return
        cached = (
            analysis_job.cached_inventory(self._instance, self._sha, self._key)
            if self._instance and self._sha is not None
            else None
        )
        if cached is not None:  # the usual turn: no DB read, no indirection
            effective, _ = apply_overrides(cached, config.overrides)
            self.tools = build_builder_tools(
                ctx, self._load_template, effective, self._messages
            )
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

    def _messages(self) -> Sequence[BaseMessage]:
        return self._history

    def _default_tools(self, platform: Optional[PlatformDefault]) -> List[BaseTool]:
        """Tools on the platform default, else the built-in template, with the
        manager's edits from the snapshot; the agent's own never apply here."""
        content, inventory = builtin_template()
        if platform is not None:
            inventory = platform.inventory
        sha = platform.sha if platform is not None else None

        async def load() -> bytes:
            if sha is None:
                return content
            return await analysed_template(PLATFORM_ID, sha)

        return build_builder_tools(self._ctx, load, inventory, self._messages)

    async def _load_template(self) -> bytes:
        # The analysed bytes, not the asset: a save rewrites the asset first.
        if self._sha is None or not self._instance:
            raise LookupError("ppt_builder: no analysed template on this turn.")
        return await analysed_template(self._instance, self._sha)

    async def _resolve(self) -> Optional[List[BaseTool]]:
        if self._resolved is not None:
            return self._resolved
        if self._sha is None:  # the pod's first read of the platform default
            self._resolved = self._default_tools(
                await analysis_job.refresh_platform_default()
            )
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
        self._resolved = build_builder_tools(
            self._ctx, self._load_template, effective, self._messages
        )
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
        self._history = request.messages
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
        if answer_closed(request.messages):
            # A proposal or a delivery ends the answer: the model can only reply,
            # so it cannot loop on the result's notes. The user's next message lifts it.
            update["tool_choice"] = "none"
        return await handler(request.override(**update))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """Builds sent together in one model round: the first one only; the
        others are answered, not failed, as the round still runs one build."""
        call = request.tool_call
        if call.get("name") == BUILD_TOOL_NAME:
            state = request.state
            messages = (
                state.get("messages", ()) if isinstance(state, Mapping) else state
            )
            refusal = round_refusal(
                messages if isinstance(messages, Sequence) else (), call.get("id")
            )
            if refusal is not None:
                text, artifact = _answer(refusal)
                return ToolMessage(
                    content=text,
                    artifact=artifact,
                    tool_call_id=call["id"],
                    name=BUILD_TOOL_NAME,
                )
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
            # All belong to the plugin's widget (rendered once): the vision toggle
            # depends on the team's models, the variety row is one sentence of two selects.
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
            FieldSpec(
                key="variety_check",
                type="select",
                default="template_slide",
                enum=list(get_args(VarietyCheck)),
                title="capability.ppt_builder.fields.variety_check.title",
                description="capability.ppt_builder.fields.variety_check.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
            FieldSpec(
                key="validate_plan",
                type="boolean",
                default=False,
                title="capability.ppt_builder.fields.validate_plan.title",
                description="capability.ppt_builder.fields.validate_plan.description",
                ui=UIHints(widget="ppt_builder_template"),
            ),
            FieldSpec(
                key="variety_max_uses",
                type="integer",
                default=2,
                min=1,
                max=5,
                title="capability.ppt_builder.fields.variety_check.title",
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
        tables=[AnalysisRow, DeckPlanRow],
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
        _require_agent_instance(ctx.identity.agent_instance_id)
        template_uploads = list(uploads.get(TEMPLATE_SLOT, ()))
        if template_uploads:
            return await self._accept_upload(config, template_uploads[0].content, ctx)
        if config.template_sha256 is None:  # pattern edits belong to a template
            return config.model_copy(update={"overrides": []})
        instance = ctx.identity.agent_instance_id
        if not instance or not ctx.identity.team_id:
            return config

        store = get_analysis_store()
        record = await store.get(instance)
        _require_own_row(record, ctx.identity.team_id)
        key = config.labelling_key()
        if record is None or record.template_sha256 != config.template_sha256:
            # The stored file is what gets analysed, whatever sha the client sent.
            sha = await self._start_from_assets(config, ctx)
            return config.model_copy(update={"template_sha256": sha})
        if self._needs_rerun(record, key, ctx.services.capability_model is not None):
            analysis_job.remember_port(instance, ctx.services.capability_model)
            await restart_from_stored(store, record, labelling_key=key)
        else:
            if record.outdated():
                analysis_job.remember_port(instance, ctx.services.capability_model)
                await refresh_outdated(store, record, force=True)
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
    def _needs_rerun(record: AnalysisRecord, key: str, has_port: bool) -> bool:
        # A rules row serves a vision config: re-run it only where vision can run.
        relabel = record.labelling_key != key and (
            has_port or record.labelling_key != analysis_job.RULES_KEY
        )
        return (
            relabel
            or record.status == "failed"
            or record.interrupted(analysis_job._utcnow())
        )

    async def _accept_upload(
        self, config: PptBuilderConfig, content: bytes, ctx: SaveContext
    ) -> PptBuilderConfig:
        early = _bounded_analysis(content)
        if early is not None:
            raise ValueError(early.errors[0].message)
        if not acquire_heavy_job_slot():
            raise RuntimeError(_BUSY_MESSAGE)
        try:
            content = await asyncio.to_thread(_check_readable, content)
        finally:
            release_heavy_job_slot()
        instance = ctx.identity.agent_instance_id
        if instance:  # before anything is stored
            record = await get_analysis_store().get(instance, with_inventory=False)
            _require_own_row(record, ctx.identity.team_id)
        assets = ctx.services.agent_assets
        if assets is None:
            logger.error("[PPTBUILD] no agent_assets port on this save path")
            raise ValueError(_STORE_UNAVAILABLE)
        await assets.store(
            PPT_BUILDER_TEMPLATE_KEY,
            content,
            content_type=_PPTX_CONTENT_TYPE,
            filename=PPT_BUILDER_TEMPLATE_KEY,
        )
        sha = await self._launch(config, content, ctx)
        return config.model_copy(
            update={"template_sha256": sha, "template_key": PPT_BUILDER_TEMPLATE_KEY}
        )

    async def _start_from_assets(
        self, config: PptBuilderConfig, ctx: SaveContext
    ) -> str:
        assets = ctx.services.agent_assets
        if assets is None:
            logger.error("[PPTBUILD] no agent_assets port on this save path")
            raise ValueError(_STORE_UNAVAILABLE)
        try:
            content = await assets.fetch(PPT_BUILDER_TEMPLATE_KEY)
            # Maybe stored before uploads were sanitised: the analysed copy is.
            content = await asyncio.to_thread(sanitize_template, content)
        except Exception as exc:  # noqa: BLE001 - the author can upload it again
            raise ValueError(
                "The stored template could not be read; upload it again."
            ) from exc
        return await self._launch(config, content, ctx)

    @staticmethod
    async def _launch(
        config: PptBuilderConfig, content: bytes, ctx: SaveContext
    ) -> str:
        instance = ctx.identity.agent_instance_id
        team = ctx.identity.team_id
        if not instance or not team:
            logger.error(
                "[PPTBUILD] template save without agent (%s) or team (%s)",
                instance,
                team,
            )
            raise ValueError(
                "The template can only be added to an agent saved in a team. Save the "
                "agent first, then add the template again."
            )
        return await start_analysis(
            instance_id=instance,
            team_id=team,
            saved_by=ctx.identity.user_id,
            content=content,
            key=config.labelling_key(),
            port=ctx.services.capability_model,
        )

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
