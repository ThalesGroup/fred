# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Explicit selection enters ordinary checkpoint messages before inference."""

import asyncio
from typing import cast

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    RuntimeServices,
    StatusRuntimeEvent,
)
from langchain_core.messages import BaseMessage, HumanMessage

from fred_runtime.react.react_tracing import tool_span
from fred_runtime.runtime_support.tool_execution import ToolExecution
from fred_runtime.skills.tools import load_skill


async def preload_skills(
    graph_input: object,
    binding: BoundRuntimeContext,
    services: RuntimeServices,
    config: ExecutionConfig,
) -> tuple[object, tuple[StatusRuntimeEvent, ...]]:
    """Use the common loader/audit boundary on fresh user-selected turns only."""
    selections = binding.runtime_context.selected_skills
    if not selections or config.resume_payload is not None:
        return graph_input, ()
    skills = services.skills
    if skills is None:
        raise ValueError("Platform skills are unavailable on this runtime")

    # Direct executor callers also fail the whole selection before any load event.
    for selection in selections:
        skills.read(selection.name)

    async def load(name: str) -> tuple[HumanMessage, StatusRuntimeEvent]:
        load_id = (
            "skill:"
            + (
                binding.runtime_context.exchange_id
                or binding.portable_context.request_id
            )
            + ":"
            + name
        )

        async def read() -> tuple[str, StatusRuntimeEvent]:
            content, attribution = load_skill(
                skills,
                name,
                origin="user",
                load_id=load_id,
                agent_id=binding.portable_context.agent_id or "agent",
                kpi=services.kpi_writer,
                binding=binding,
            )
            return content, StatusRuntimeEvent(
                status="skill_loaded", skill_load=attribution
            )

        async with tool_span(
            services.tracer,
            name="tool.invoke",
            context=binding.portable_context,
            attributes={"tool_name": "load_skill", "origin": "user"},
            input_payload={"name": name},
        ) as span:
            content, event = await ToolExecution(
                kpi=services.kpi_writer, binding=binding
            ).run(
                read,
                tool_name="load_skill",
                source="platform",
                span=span,
            )
            if (
                span is not None
                and services.tracer is not None
                and services.tracer.captures_content
            ):
                span.set_io(output=content)
        return HumanMessage(content=content, id=load_id), event

    loaded = await asyncio.gather(*(load(selection.name) for selection in selections))
    base = cast(dict[str, object], graph_input)
    messages = cast(list[BaseMessage], base["messages"])
    return {
        **base,
        "messages": [*(message for message, _ in loaded), *messages],
    }, tuple(event for _, event in loaded)
