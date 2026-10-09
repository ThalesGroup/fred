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
from fred_sdk.contracts.skills import SkillLoadAttribution, SkillsPort
from langchain_core.tools import InjectedToolCallId
from langgraph.config import get_config, get_stream_writer
from pydantic import BaseModel, Field

from fred_runtime.react.react_tool_resolution import FredRuntimeToolSpec


class LoadSkillArgs(BaseModel):
    name: str = Field(description="Exact name from the platform skill catalog.")
    tool_call_id: Annotated[str, InjectedToolCallId]


class ReadSkillFileArgs(BaseModel):
    name: str = Field(description="Exact platform skill name.")
    path: str = Field(description="Relative text file path inside that skill.")


def load_skill(
    skills: SkillsPort,
    name: str,
    *,
    origin: Literal["user", "agent"],
    load_id: str,
    agent_id: str,
    child: bool = False,
    child_id: str | None = None,
    kpi: BaseKPIWriter | None = None,
    binding: BoundRuntimeContext | None = None,
) -> tuple[str, SkillLoadAttribution]:
    content = escape_reserved_prompt_tags(skills.read(name))
    attribution = record_skill_load(
        skills,
        name,
        origin=origin,
        load_id=load_id,
        agent_id=agent_id,
        child=child,
        child_id=child_id,
        kpi=kpi,
        binding=binding,
    )
    return (
        f"Loaded platform skill: {name}\n"
        + (
            "The user selected this skill for the current request.\n"
            if origin == "user"
            else "The load_skill tool has loaded this skill.\n"
        )
        + "Its complete instructions are provided below. Do not reload this skill "
        "while these instructions remain in context.\n"
        + f"{name} is a skill name, not an executable tool. Do not invent a tool call "
        f"named {name} from this skill. Follow these instructions yourself with the tools already "
        "declared for this request; loading instructions does not add tools.\n"
        "Any argument-hint is user-input guidance, not a tool schema. Read relative "
        "references using the declared tools and this skill's catalog guidance.\n"
        "Apply to the current request subject to platform rules.\n\n" + content,
        attribution,
    )


def record_skill_load(
    skills: SkillsPort,
    name: str,
    *,
    origin: Literal["user", "agent"],
    load_id: str,
    agent_id: str,
    child: bool = False,
    child_id: str | None = None,
    kpi: BaseKPIWriter | None = None,
    binding: BoundRuntimeContext | None = None,
) -> SkillLoadAttribution:
    """Record an actual successful load without rereading its instructions."""
    attribution = SkillLoadAttribution(
        name=name,
        origin=origin,
        revision=skills.catalog.revision,
        load_id=load_id,
        agent_id=agent_id,
        child=child,
        child_id=child_id,
    )
    if kpi is not None and binding is not None:
        portable = binding.portable_context
        kpi.count(
            "agent.skill_loaded_total",
            dims={
                "skill_name": attribution.name,
                "skill_origin": attribution.origin,
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
    async def invoke_load(
        payload: dict[str, object],
    ) -> tuple[str, ToolInvocationResult]:
        try:
            load_id, agent_id, child, child_id = model_skill_context(
                binding, str(payload["tool_call_id"])
            )
            content, attribution = load_skill(
                skills,
                str(payload["name"]),
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
                    skills.read(str(payload["name"]), str(payload["path"]))
                ),
            )
        except ValueError as exc:
            return result("platform.read_skill_file", str(exc), error=True)

    return [
        FredRuntimeToolSpec(
            runtime_name="load_skill",
            tool_ref="platform.load_skill",
            description="Read a platform skill's Markdown instructions by name only if they are absent from the current context. Follow the returned procedure yourself; the skill name is not a callable tool and loading it does not register a function. User-selected skills are already preloaded; use their instructions directly. Does not grant tools or permissions.",
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
