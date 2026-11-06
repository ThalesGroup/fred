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

"""``PptBuilderCapability``: a deck from a chat plan on an analysed or built-in template.
The save never waits on the analysis (``analysis_job`` runs it, ``readiness`` holds the
agent until it succeeds); the preview part and side pane are ``ppt_filler``'s."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, List, Optional, get_args

from fastapi import APIRouter, Depends, HTTPException
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
    ScopePrivate,
    SidePanelSpec,
    UploadedFile,
)
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationResult,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import (
    CapabilityTeamAuthorizer,
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
    AnalysisRecord,
    AnalysisRow,
    AnalysisStatusResponse,
    analysed_template,
    analysis_readiness,
    get_analysis_store,
    labelling_key,
    ready_inventory,
    status_response,
)
from fred_capability_ppt_filler.builder.assign import VarietyCheck
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.deck_plans import DeckPlanRow
from fred_capability_ppt_filler.builder.models import (
    AnalysisError,
    AnalyzeResult,
    PatternOverride,
)
from fred_capability_ppt_filler.builder.overrides import (
    apply_overrides,
)
from fred_capability_ppt_filler.builder.preview import build_patterns_deck
from fred_capability_ppt_filler.builder.tools import (
    ASK_USER,
    BUILD_TOOL_NAME,
    PPT_BUILDER_CAPABILITY_ID,
    _answer,
    _error,
    answer_stage,
    approval_question,
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


class CommonTemplateConfig(BaseModel):
    """Organization/pod template corrections supplied by Control Plane."""

    overrides: List[PatternOverride] = []


class PptBuilderConfig(BaseModel):
    """Stored config (ConfigModel == StoredConfigModel). ``template_sha256``
    names the analysed template; ``None`` means the built-in template. The
    analysis itself lives in ``cap_ppt_builder_analysis``."""

    # Set only for an uploaded template, so a copy re-submits that file alone.
    template_key: Annotated[Optional[str], AssetKey(TEMPLATE_SLOT)] = None
    template_sha256: Optional[str] = None
    analysis_id: ScopePrivate[Optional[str]] = None
    common_template_config: Optional[CommonTemplateConfig] = None
    use_vision: bool = False
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

    def effective_overrides(self) -> List[PatternOverride]:
        common = (
            self.common_template_config.overrides if self.common_template_config else []
        )
        # Agent patches win field by field over the common template corrections.
        merged = {
            item.pattern_id: item.model_dump(exclude_none=True) for item in common
        }
        for item in self.overrides:
            merged.setdefault(item.pattern_id, {}).update(
                item.model_dump(exclude_none=True)
            )
        return [PatternOverride.model_validate(item) for item in merged.values()]

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


def _check_readable(content: bytes) -> bytes:
    """The upload as stored: sanitised, and opened to fail the save on an
    unreadable .pptx (cheap: opening, not analysing)."""
    try:
        content = sanitize_template(content)
        open_presentation(content)
    except UnsafeArchiveError as exc:
        raise ValueError(f"The uploaded file could not be read: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a template error
        logger.info("unreadable template upload: %s", type(exc).__name__)
        raise ValueError(unreadable_message(content)) from exc
    return content


async def _authorised_record(
    instance_id: str,
    authorizer: CapabilityTeamAuthorizer,
    space_id: str | None = None,
    agent_instance_id: str | None = None,
) -> AnalysisRecord:
    # Legacy platform rows are never a valid agent analysis or file authority.
    record = (
        None
        if instance_id in (PLATFORM_ID, PLATFORM_NEXT_ID, BUILTIN_ID)
        else await get_analysis_store().get(instance_id)
    )
    if record is None or (
        instance_id.startswith("prep:")
        and record.saved_by != f"runtime:{authorizer.runtime_id}"
    ):
        raise HTTPException(status_code=404, detail="No template analysis.")
    if instance_id.startswith("prep:"):
        if not space_id:
            raise HTTPException(status_code=422, detail="A usage space is required.")
        await authorizer.require_preparation_access(
            instance_id, space_id, agent_instance_id
        )
    else:
        await authorizer.require_agent_editor(record.team_id)
    return record


def _build_router() -> APIRouter:
    router = APIRouter(tags=["ppt_builder"])

    @router.get(
        "/builtin", response_model=AnalyzeResult, operation_id="getPptBuilderBuiltin"
    )
    async def builtin(
        space_id: str | None = None, runtime_id: str | None = None
    ) -> AnalyzeResult:
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
        space_id: str | None = None,
        agent_instance_id: str | None = None,
        runtime_id: str | None = None,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> AnalysisStatusResponse:
        """Status, summary and inventory of the instance's template analysis."""
        return status_response(
            await _authorised_record(
                instance_id, authorizer, space_id, agent_instance_id
            )
        )

    @router.get(
        "/analysis/{instance_id}/patterns.pdf",
        operation_id="getPptBuilderAnalysisPatterns",
    )
    async def analysis_patterns(
        instance_id: str,
        space_id: str | None = None,
        agent_instance_id: str | None = None,
        runtime_id: str | None = None,
        authorizer: CapabilityTeamAuthorizer = Depends(capability_team_authorizer),
    ) -> Response:
        """One PDF page per pattern of the analysed template (the thumbnails)."""
        await _authorised_record(instance_id, authorizer, space_id, agent_instance_id)
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
    True: "the built-in template (this agent has no activated template of its own)",
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
    "A delivered deck ends the answer: no tool can be called after it, so tell "
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
    "directly means calling the tool: when it proposes a plan, do what its result says (ask with "
    "ask_user, or show the outline and end your answer); the deck is built only once the user "
    "approved it.",
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
    """Build tools plus working rules on the system prompt. The analysis is read on the
    first model call (cached per template per pod) and the tool refuses until it has
    succeeded; without an activated template, the built-in file is used."""

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
        self._can_ask = False
        config = ctx.config
        identity = ctx.identity
        self._sha = config.template_sha256
        self._instance = config.analysis_id or identity.agent_instance_id
        self._key = config.labelling_key()

        if self._sha is None:
            self.tools = self._default_tools()
            self._resolved = self.tools
            return
        cached = (
            analysis_job.cached_inventory(self._instance, self._sha, self._key)
            if self._instance and self._sha is not None
            else None
        )
        if cached is not None:  # the usual turn: no DB read, no indirection
            effective, _ = apply_overrides(cached, config.effective_overrides())
            self.tools = build_builder_tools(
                ctx, self._load_template, effective, self._messages, self._asks
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

    def _asks(self) -> bool:
        return self._can_ask

    def _default_tools(self) -> List[BaseTool]:
        """Only the bundled file is executable until CP-owned preparation is wired."""
        content, inventory = builtin_template()
        common = self._ctx.config.common_template_config
        inventory, _ = apply_overrides(inventory, common.overrides if common else [])

        async def load() -> bytes:
            return content

        return build_builder_tools(
            self._ctx, load, inventory, self._messages, self._asks
        )

    async def _load_template(self) -> bytes:
        # The analysed bytes, not the asset: a save rewrites the asset first.
        if self._sha is None or not self._instance:
            raise LookupError("ppt_builder: no analysed template on this turn.")
        return await analysed_template(self._instance, self._sha)

    async def _resolve(self) -> Optional[List[BaseTool]]:
        if self._resolved is not None:
            return self._resolved
        if not self._instance or self._sha is None:
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
        effective, _ = apply_overrides(
            inventory, self._ctx.config.effective_overrides()
        )
        self._resolved = build_builder_tools(
            self._ctx, self._load_template, effective, self._messages, self._asks
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
        offered = {
            getattr(t, "name", None): t for t in update.get("tools", request.tools)
        }
        self._can_ask = ASK_USER in offered
        stage = answer_stage(request.messages)
        if stage == "proposed" and self._can_ask:
            # The plan is approved by its button only: the model asks, nothing else.
            update["tools"], update["tool_choice"] = [offered[ASK_USER]], "any"
        elif stage == "approved" and BUILD_TOOL_NAME in offered:
            update["tools"], update["tool_choice"] = [offered[BUILD_TOOL_NAME]], "any"
        elif stage in ("delivered", "proposed", "skipped"):
            # A delivery or an unanswered plan ends the answer: the model can only
            # reply, so it cannot loop on the result's notes.
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
        state = request.state
        if call.get("name") == ASK_USER:
            messages = (
                state.get("messages", ()) if isinstance(state, Mapping) else state
            )
            if isinstance(messages, Sequence) and answer_stage(messages) == "proposed":
                args = approval_question(messages, call.get("args") or {})
                return await handler(request.override(tool_call={**call, "args": args}))
        if call.get("name") == BUILD_TOOL_NAME:
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
                default=False,
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
        """Bounded preflight only. Accepted preparation is owned by CP/Temporal."""
        del ctx
        files = list(uploads.get(TEMPLATE_SLOT, ()))
        if files:
            content = files[0].content
            early = _bounded_analysis(content)
            if early is not None:
                raise ValueError(early.errors[0].message)
            # The slot remains occupied if cancellation leaves the parser thread running.
            await asyncio.wait_for(
                analysis_job._cpu(_check_readable, content), timeout=10
            )
        if config.use_vision:
            raise ValueError(
                "Template vision labeling is not connected to Weaver inference admission."
            )
        # Neither a browser's analysis reference nor its claimed digest is authority.
        return config.model_copy(
            update={
                "template_sha256": None,
                "analysis_id": None,
                "template_key": None,
                "common_template_config": None,
            }
        )

    async def prepare(self, ctx: PreparationContext) -> PreparationResult:
        from .preparation import prepare

        return await prepare(ctx)

    async def retire_preparation(self, ctx: PreparationContext) -> None:
        from .preparation import retire

        await retire(ctx)

    async def readiness(
        self, stored: PptBuilderConfig, identity: CapabilityIdentity
    ) -> CapabilityReadiness:
        """Ready on the built-in template or once the template analysis succeeded."""
        instance = stored.analysis_id or identity.agent_instance_id
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
