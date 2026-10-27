# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Request eligibility and attribution around DeepAgents' native skill loader.

The library owns discovery metadata, pinning, body reads and skill prompts.
Fred supplies the current policy view and observes successful native pins.
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
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langgraph.types import Command

from fred_runtime.skills.catalog import PlatformSkills
from fred_runtime.skills.tools import model_skill_context, record_skill_load


class NativeSkillState(SkillsState):
    fred_pending_skill_names: NotRequired[list[str]]


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
        summaries = {s.name: s for s in self.skills.catalog.skills}
        pending = tuple(
            cast(NativeSkillState, request.state).get("fred_pending_skill_names") or ()
        )
        updates: list[HumanMessage] = []
        found: set[str] = set()
        actual: list[tuple[str, str]] = []
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
            # Sanitize every retained native pin, even after model failure or
            # policy changes. Native before_model checkpointed its raw message
            # before this wrapper; an LLM failure cannot be a safety boundary.
            fresh = (
                index > last_user
                and name in pending
                and name in summaries
                and not message.additional_kwargs.get("fred_skill_observed")
            )
            if fresh:
                found.add(name)
                actual.append((name, str(message.id)))
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
                            if fresh
                            else {}
                        ),
                    },
                }
            )
            if fresh or safe_content != message.content:
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
        by_id = {m.id: m for m in updates}
        if updates:
            request = request.override(
                messages=[by_id.get(m.id, m) for m in request.messages]
            )
        response = await handler(request)
        return (
            ExtendedModelResponse(
                model_response=response,
                command=Command(
                    update={"messages": updates, "fred_pending_skill_names": []}
                ),
            )
            if updates
            else response
        )
