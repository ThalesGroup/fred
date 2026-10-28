# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Request eligibility and attribution around DeepAgents' native skill loader.

The library owns discovery metadata, pinning, body reads and skill prompts.
Fred supplies eligibility and identifies complete pins already in context.
"""

from collections.abc import Awaitable, Callable
from typing import Any, NotRequired, cast

from deepagents.middleware.skills import SkillsState
from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.prompt_utils import escape_reserved_prompt_tags
from fred_sdk.contracts.runtime import StatusRuntimeEvent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ExtendedModelResponse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langgraph.types import Command

from fred_runtime.skills.catalog import PlatformSkills
from fred_runtime.skills.tools import model_skill_context, record_skill_load

NATIVE_SKILLS_SYSTEM_PROMPT = (
    "## Skills System\n\n"
    "Skills are procedures for you to follow using the declared tools.\n\n"
    "{skills_locations}{skills_load_warnings}\n\n"
    "Available skills:\n\n{skills_list}\n\n"
    "Required skill selection: before answering or using any other tool, "
    "including task delegation, you MUST compare the request with the available "
    "skill descriptions and apply every matching skill. Read its complete "
    "instructions first with read_file at the catalog path (limit=1000; continue "
    "if truncated), unless the complete instructions are already in context. "
    "Reuse complete pinned instructions without rereading SKILL.md. Read any "
    "missing required references. Familiarity with the task does not replace "
    "reading and following the skill procedure. "
    "Match skills to the requested output, including routine tasks: a request "
    "for a diagram or chart calls for an available diagram/chart skill even "
    "when the user names only the process to illustrate. Start by reading "
    "that procedure, then its required references, before drafting the output "
    "or calling a rendering tool."
)


class NativeSkillState(SkillsState):
    fred_pending_skill_names: NotRequired[list[str]]
    fred_observed_pin_ids: NotRequired[list[str]]


class NativeSkillPolicyMiddleware(AgentMiddleware[NativeSkillState, Any]):
    state_schema = NativeSkillState

    def __init__(
        self,
        skills: PlatformSkills,
        binding: BoundRuntimeContext,
        kpi: BaseKPIWriter | None = None,
    ) -> None:
        self.skills = skills.for_execution(
            tuple(s.name for s in binding.runtime_context.selected_skills),
            binding.disabled_platform_skills,
            resuming=binding.is_resuming,
        )
        self.binding = binding
        self.kpi = kpi

    def before_agent(self, state: NativeSkillState, runtime: Runtime) -> dict[str, Any]:
        return {
            "skills_metadata": self.skills.native_metadata,
            "skills_load_errors": [],
            "fred_pending_skill_names": [],
            "fred_observed_pin_ids": [],
        }

    async def abefore_agent(
        self, state: NativeSkillState, runtime: Runtime
    ) -> dict[str, Any]:
        return self.before_agent(state, runtime)

    def before_model(self, state: NativeSkillState, runtime: Runtime) -> dict[str, Any]:
        # Also refresh on HITL resume, where before_agent may not run. Native
        # SkillsMiddleware executes after this hook and consumes pinned_skills.
        return {
            "skills_metadata": self.skills.native_metadata,
            "skills_load_errors": [],
            # Graph state isolates concurrent child/checkpoint namespaces. A
            # middleware instance can be shared by several native child calls.
            "fred_pending_skill_names": list(state.get("pinned_skills") or ()),
            "fred_observed_pin_ids": [],
        }

    async def abefore_model(
        self, state: NativeSkillState, runtime: Runtime
    ) -> dict[str, Any]:
        return self.before_model(state, runtime)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | ExtendedModelResponse:
        """Observe native pins and tell the model which instructions it already has."""
        summaries = {s.name: s for s in self.skills.catalog.skills}
        pending = tuple(
            cast(NativeSkillState, request.state).get("fred_pending_skill_names") or ()
        )
        observed = cast(NativeSkillState, request.state).setdefault(
            "fred_observed_pin_ids", []
        )
        updates: list[HumanMessage] = []
        found: set[str] = set()
        actual: list[tuple[str, str]] = []
        loaded: dict[str, None] = {}
        last_user = max(
            (
                i
                for i, m in enumerate(request.messages)
                if isinstance(m, HumanMessage)
                and m.additional_kwargs.get("lc_source") != "pinned_skill"
            ),
            default=-1,
        )
        for index, message in enumerate(request.messages):
            if (
                not isinstance(message, HumanMessage)
                or message.additional_kwargs.get("lc_source") != "pinned_skill"
            ):
                continue
            marker = message.additional_kwargs.get("skill")
            name = marker.get("name") if isinstance(marker, dict) else None
            if not isinstance(marker, dict) or not isinstance(name, str):
                continue
            message_id = str(message.id)
            if name in summaries:
                loaded[name] = None
            # Sanitize every retained native pin, even after model failure or
            # policy changes. Native before_model checkpointed its raw message
            # before this wrapper; an LLM failure cannot be a safety boundary.
            requested_pin = index > last_user and name in pending and name in summaries
            if requested_pin:
                found.add(name)
                if message_id not in observed and not message.additional_kwargs.get(
                    "fred_skill_observed"
                ):
                    actual.append((name, message_id))
            safe_content = escape_reserved_prompt_tags(str(message.content))
            updated = message.model_copy(
                update={
                    "content": safe_content,
                    "additional_kwargs": {
                        **message.additional_kwargs,
                        **(
                            {
                                "fred_skill_observed": True,
                                "skill": {**marker, "builtin": summaries[name].builtin},
                            }
                            if requested_pin
                            else {}
                        ),
                    },
                }
            )
            if requested_pin or safe_content != message.content:
                updates.append(updated)
        if set(pending) - found:
            raise ValueError("Selected skill could not be pinned by the native loader")
        for name, message_id in actual:
            load_id, agent_id, child, child_id = model_skill_context(
                self.binding, "pin:" + message_id
            )
            attribution = record_skill_load(
                self.skills,
                name,
                origin="user",
                load_id=load_id,
                agent_id=agent_id,
                child=child,
                child_id=child_id,
                kpi=self.kpi,
                binding=self.binding,
            )
            get_stream_writer()(
                StatusRuntimeEvent(status="skill_loaded", skill_load=attribution)
            )
            # Recovery reenters before Commands commit, sharing request.state.
            # before_model resets this list for each graph model invocation.
            observed.append(message_id)
        by_id = {m.id: m for m in updates}
        if updates:
            request = request.override(
                messages=[by_id.get(m.id, m) for m in request.messages]
            )
        notices: list[str] = []
        if loaded:
            notices.append(
                "Already-loaded skill instructions: "
                + ", ".join(f"`{name}`" for name in loaded)
                + ". Their complete instructions are present in this conversation. "
                "Apply them directly when relevant to the current request. "
                "Do not read their SKILL.md files again while those instructions "
                "remain in context. Read any required references that are still missing."
            )
        if notices:
            system = request.system_message or SystemMessage(content="")
            request = request.override(
                system_message=system.model_copy(
                    update={
                        "content": [
                            *system.content_blocks,
                            {"type": "text", "text": "\n\n" + "\n\n".join(notices)},
                        ]
                    }
                )
            )
        response = await handler(request)
        return (
            ExtendedModelResponse(
                model_response=response,
                command=Command(
                    update={
                        "messages": updates,
                        "fred_pending_skill_names": [],
                        "fred_observed_pin_ids": [],
                    }
                ),
            )
            if updates
            else response
        )
