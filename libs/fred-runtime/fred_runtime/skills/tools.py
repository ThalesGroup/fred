# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Shared procedural reads through Fred's existing tool binding and tracing."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.prompt_utils import escape_reserved_prompt_tags
from fred_sdk.contracts.runtime import StatusRuntimeEvent
from fred_sdk.contracts.skills import SkillInvocation, SkillLoadAttribution, SkillsPort
from langchain_core.tools import InjectedToolCallId
from langgraph.config import get_config, get_stream_writer
from pydantic import BaseModel, Field

from fred_runtime.react.react_tool_resolution import FredRuntimeToolSpec


class LoadSkillArgs(BaseModel):
    skill_id: str = Field(
        description="Exact skill_id from the admitted catalog, not the skill name."
    )
    tool_call_id: Annotated[str, InjectedToolCallId]


class ReadSkillFileArgs(BaseModel):
    skill_id: str = Field(description="Exact platform skill skill_id.")
    path: str = Field(description="Relative text file path inside that skill.")


def load_skill(
    skills: SkillsPort,
    skill_id: str,
    *,
    origin: Literal["user", "agent"],
    load_id: str,
    agent_id: str,
    child: bool = False,
    child_id: str | None = None,
    kpi: BaseKPIWriter | None = None,
    binding: BoundRuntimeContext | None = None,
) -> tuple[str, SkillLoadAttribution]:
    from fred_runtime.skills.catalog import PlatformSkills

    if origin == "user" and any(
        s.skill_id == skill_id and not s.user_invocable for s in skills.catalog.skills
    ):
        raise ValueError("Skill is not user-invocable")
    if isinstance(skills, PlatformSkills):
        selections = (
            binding.runtime_context.selected_skills
            if binding is not None
            else tuple(
                SkillInvocation(skill_id=s.skill_id, space_id=s.space_id, name=s.name)
                for s in skills.catalog.skills
                if s.skill_id == skill_id and origin == "user"
            )
        )
        skills = skills.for_execution(
            selections,
            binding.unavailable_skill_ids if binding is not None else (),
            resuming=binding.is_resuming if binding is not None else False,
        )
    content = escape_reserved_prompt_tags(skills.read(skill_id))
    attribution = record_skill_load(
        skills,
        skill_id,
        origin=origin,
        load_id=load_id,
        agent_id=agent_id,
        child=child,
        child_id=child_id,
        kpi=kpi,
        binding=binding,
    )
    return (
        f"Loaded platform skill: {attribution.name} ({escape_reserved_prompt_tags(attribution.space_name)}; {skill_id})\n"
        + (
            "The user selected this skill for the current request.\n"
            if origin == "user"
            else "The load_skill tool has loaded this skill.\n"
        )
        + "Its complete instructions are provided below. Do not reload this skill "
        "while these instructions remain in context.\n"
        + f"{attribution.name} is a skill name, not an executable tool. Do not invent a tool call "
        f"named {attribution.name} from this skill. Follow these instructions yourself with the tools already "
        "declared for this request; loading instructions does not add tools.\n"
        "Any argument-hint is user-input guidance, not a tool schema. Read relative "
        "references using the declared tools and this skill's catalog guidance.\n"
        "Apply to the current request subject to platform rules.\n\n" + content,
        attribution,
    )


def record_skill_load(
    skills: SkillsPort,
    skill_id: str,
    *,
    origin: Literal["user", "agent"],
    load_id: str,
    agent_id: str,
    child: bool = False,
    child_id: str | None = None,
    partial: bool = False,
    kpi: BaseKPIWriter | None = None,
    binding: BoundRuntimeContext | None = None,
) -> SkillLoadAttribution:
    """Record an actual successful load without rereading its instructions."""
    summary = next((s for s in skills.catalog.skills if s.skill_id == skill_id), None)
    if summary is None:
        raise ValueError("Skill unavailable in this runtime catalog")
    attribution = SkillLoadAttribution(
        skill_id=skill_id,
        space_id=summary.space_id,
        space_name=summary.space_name,
        name=summary.name,
        origin=origin,
        revision=skills.catalog.revision,
        load_id=load_id,
        agent_id=agent_id,
        child=child,
        child_id=child_id,
        partial=partial,
        builtin=any(
            s.skill_id == skill_id and s.builtin for s in skills.catalog.skills
        ),
    )
    if kpi is not None and binding is not None:
        portable = binding.portable_context
        kpi.count(
            "agent.skill_loaded_total",
            dims={
                "skill_name": attribution.name,
                "skill_id": attribution.skill_id,
                "skill_space_id": attribution.space_id,
                "skill_origin": attribution.origin,
                "space_id": portable.space_id,
                "team_id": portable.team_id,
                "session_id": portable.session_id,
                "exchange_id": binding.runtime_context.exchange_id,
                "user_id": portable.user_id,
                "agent_instance_id": portable.baggage.get("agent_instance_id"),
                "template_agent_id": attribution.agent_id,
            },
            actor=KPIActor(type="system"),
        )
    return attribution


def model_skill_context(
    binding: BoundRuntimeContext, tool_call_id: str
) -> tuple[str, str, bool, str | None]:
    namespace = str(get_config().get("metadata", {}).get("langgraph_checkpoint_ns", ""))
    child = "|" in namespace
    child_id = hashlib.sha256(namespace.encode()).hexdigest()[:16] if child else None
    return (
        (child_id + ":" if child_id else "") + tool_call_id,
        "general-purpose"
        if child
        else binding.runtime_context.template_agent_id
        or binding.portable_context.agent_id
        or "agent",
        child,
        child_id,
    )


def build_skill_tools(
    skills: SkillsPort, binding: BoundRuntimeContext, kpi: BaseKPIWriter | None = None
) -> list[FredRuntimeToolSpec]:
    from fred_runtime.skills.catalog import PlatformSkills

    if isinstance(skills, PlatformSkills):
        skills = skills.for_execution(
            binding.runtime_context.selected_skills,
            binding.unavailable_skill_ids,
            resuming=binding.is_resuming,
        )

    async def invoke_load(
        payload: dict[str, object],
    ) -> tuple[str, ToolInvocationResult]:
        try:
            load_id, agent_id, child, child_id = model_skill_context(
                binding, str(payload["tool_call_id"])
            )
            content, attribution = load_skill(
                skills,
                str(payload["skill_id"]),
                origin="agent",
                load_id=load_id,
                agent_id=agent_id,
                child=child,
                child_id=child_id,
                kpi=kpi,
                binding=binding,
            )
        except ValueError as exc:
            return result("platform.load_skill", str(exc), error=True)
        get_stream_writer()(
            StatusRuntimeEvent(status="skill_loaded", skill_load=attribution)
        )
        return result("platform.load_skill", content)

    async def invoke_read(
        payload: dict[str, object],
    ) -> tuple[str, ToolInvocationResult]:
        try:
            return result(
                "platform.read_skill_file",
                escape_reserved_prompt_tags(
                    skills.read(str(payload["skill_id"]), str(payload["path"]))
                ),
            )
        except ValueError as exc:
            return result("platform.read_skill_file", str(exc), error=True)

    return [
        FredRuntimeToolSpec(
            runtime_name="load_skill",
            tool_ref="platform.load_skill",
            description="Call this first when a platform skill's description matches the user's request, even without a slash command: read that skill's Markdown instructions by its exact catalog identity before answering or using task tools. Skip only when its complete instructions are already in context, including user-preloaded skills. Follow the returned procedure yourself; the skill skill_id is not a callable tool and loading it does not register a function. Does not grant tools or permissions.",
            args_schema=LoadSkillArgs,
            invoke=invoke_load,
        ),
        FredRuntimeToolSpec(
            runtime_name="read_skill_file",
            tool_ref="platform.read_skill_file",
            description="Read a referenced text file or template inside a platform skill. Read-only; scripts cannot be executed.",
            args_schema=ReadSkillFileArgs,
            invoke=invoke_read,
        ),
    ]


def result(
    tool_ref: str, content: str, *, error: bool = False
) -> tuple[str, ToolInvocationResult]:
    return content, ToolInvocationResult(
        tool_ref=tool_ref,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=content),),
        is_error=error,
    )
