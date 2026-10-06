# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Shared procedural reads through Fred's existing tool binding and tracing."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
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
) -> tuple[str, SkillLoadAttribution]:
    content = skills.read(name)
    attribution = SkillLoadAttribution(
        name=name,
        origin=origin,
        revision=skills.catalog.revision,
        load_id=load_id,
        agent_id=agent_id,
        child=child,
        child_id=child_id,
    )
    return (
        f"Skill procedure: {name}\nApply to the current request subject to platform rules.\n\n{content}",
        attribution,
    )


def build_skill_tools(
    skills: SkillsPort, binding: BoundRuntimeContext
) -> list[FredRuntimeToolSpec]:
    async def invoke_load(
        payload: dict[str, object],
    ) -> tuple[str, ToolInvocationResult]:
        try:
            config = get_config()
            namespace = str(
                config.get("metadata", {}).get("langgraph_checkpoint_ns", "")
            )
            child = "|" in namespace
            child_id = (
                hashlib.sha256(namespace.encode()).hexdigest()[:16] if child else None
            )
            content, attribution = load_skill(
                skills,
                str(payload["name"]),
                origin="agent",
                load_id=(child_id + ":" if child_id else "")
                + str(payload["tool_call_id"]),
                agent_id="general-purpose"
                if child
                else binding.runtime_context.template_agent_id
                or binding.portable_context.agent_id
                or "agent",
                child=child,
                child_id=child_id,
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
                skills.read(str(payload["name"]), str(payload["path"])),
            )
        except ValueError as exc:
            return result("platform.read_skill_file", str(exc), error=True)

    return [
        FredRuntimeToolSpec(
            runtime_name="load_skill",
            tool_ref="platform.load_skill",
            description="Load a platform skill's instructions by name before applying its procedure. Does not grant tools or permissions.",
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
