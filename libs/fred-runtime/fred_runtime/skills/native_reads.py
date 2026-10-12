# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Attribute successful native Deep skill reads at the existing tool boundary."""

from deepagents.backends.utils import validate_path
from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.prompt_utils import escape_reserved_prompt_tags
from fred_sdk.contracts.runtime import StatusRuntimeEvent
from fred_sdk.contracts.skills import SkillsPort
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer

from .tools import model_skill_context, record_skill_load


def observe_skill_read(
    message: ToolMessage,
    args: dict[str, object],
    *,
    skills: SkillsPort,
    binding: BoundRuntimeContext,
    kpi: BaseKPIWriter | None,
) -> ToolMessage:
    """No extra read: preserve the actual returned window and native errors."""
    if message.status == "error" or not isinstance(message.content, str):
        return message
    path = args.get("file_path")
    if not isinstance(path, str):
        return message
    try:
        path = validate_path(path)
    except ValueError:
        return message
    parts = path.split("/")
    if len(parts) < 4 or parts[1] != "skills":
        return message
    name = parts[2]
    # Native read_file normalizes negative bounds and its schema coerces ints.
    raw_offset, raw_limit = args.get("offset", 0), args.get("limit", 100)
    if not isinstance(raw_offset, (int, str, float)) or not isinstance(
        raw_limit, (int, str, float)
    ):
        return message
    try:
        offset, limit = max(int(raw_offset), 0), max(int(raw_limit), 0)
    except (ValueError, OverflowError):
        return message
    if path.endswith("/SKILL.md") and offset == 0 and limit > 0:
        if path == f"/skills/{name}/SKILL.md":
            load_id, agent_id, child, child_id = model_skill_context(
                binding, message.tool_call_id
            )
            selections = binding.runtime_context.selected_skills
            attribution = record_skill_load(
                skills,
                name,
                origin="user"
                if any(selection.name == name for selection in selections)
                else "agent",
                load_id=load_id,
                agent_id=agent_id,
                child=child,
                child_id=child_id,
                kpi=kpi,
                binding=binding,
            )
            get_stream_writer()(
                StatusRuntimeEvent(status="skill_loaded", skill_load=attribution)
            )
    return message.model_copy(
        update={"content": escape_reserved_prompt_tags(message.content)}
    )
