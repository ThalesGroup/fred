# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Exercise completeness against native read windows and clipping."""

import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest
from deepagents.middleware.filesystem import FilesystemMiddleware
from fred_core.kpi import BaseKPIWriter
from fred_runtime.skills.catalog import PlatformSkills
from fred_runtime.skills.native_reads import _partial_skill_read
from fred_sdk.contracts.runtime import StatusRuntimeEvent
from fred_sdk.contracts.skills import SkillLoadAttribution
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from test_platform_skills import Model, binding, call, compiled, skill


@pytest.mark.parametrize(
    ("content", "partial"),
    [
        ("@@ lines 1-222 of 222 @@\nInstructions mention truncated results.", False),
        ("@@ lines 1-100 of 222 | next offset 100 @@\n@@ lines 1-1 of 1 @@", True),
        ("@@ lines 1-100 @@\nUnknown total", True),
        ("@@ lines 1-1 of 1 | truncated mid-line | 1 of 100 chars @@\nx", True),
        ("[Negative offset clamped to 0.]\n@@ lines 1-3 of 3 @@\nAll", False),
        ("[Output was truncated.]\n@@ lines 1-3 of 3 @@\nSome", True),
        ("Opaque output\n@@ lines 1-1 of 1 @@", True),
        ("[Notice]\n" * 300 + "@@ lines 1-1 of 1 @@", True),
    ],
)
def test_only_native_envelope_establishes_complete_coverage(
    content: str, partial: bool
) -> None:
    assert _partial_skill_read(content) is partial


async def _native_reads(
    skills: PlatformSkills, *, limit: int | None, child: bool = False
) -> tuple[list[StatusRuntimeEvent], list[ToolMessage]]:
    """Run real native tools with scripted model choices, without provider I/O."""
    args: dict[str, object] = {"file_path": "/skills/example/SKILL.md"}
    if limit is not None:
        args["limit"] = limit
    script = [call("read_file", args, "read"), AIMessage(content="done")]
    if child:
        script = [
            call(
                "task",
                {"description": "Read example", "subagent_type": "general-purpose"},
                "child",
            ),
            *script,
            AIMessage(content="parent done"),
        ]
    model = Model(script=script)
    metrics = Mock(spec=BaseKPIWriter)
    agent = compiled(model, skills, binding(), True, kpi=metrics)
    events = [
        payload
        async for _, mode, payload in agent.astream(
            {"messages": [HumanMessage(content="Read example")]},
            {"configurable": {"thread_id": "read-completeness"}},
            stream_mode=["updates", "custom"],
            subgraphs=True,
        )
        if mode == "custom"
        and isinstance(payload, StatusRuntimeEvent)
        and payload.skill_load
    ]
    counts = [
        item
        for item in metrics.count.call_args_list
        if item.args[0] == "agent.skill_loaded_total"
    ]
    assert len(events) == len(counts) == 1
    returned = [
        message
        for messages in model.calls
        for message in messages
        if isinstance(message, ToolMessage) and message.tool_call_id == "read"
    ]
    assert returned
    return events, returned


@pytest.mark.asyncio
async def test_concurrent_parent_and_child_reads_keep_independent_coverage(
    tmp_path: Path,
) -> None:
    skill(tmp_path, body="\n".join(f"instruction {i}" for i in range(218)))
    skills = PlatformSkills.from_directory(str(tmp_path))
    (partial_events, partial_text), (full_events, full_text) = await asyncio.gather(
        _native_reads(skills, limit=None, child=True),
        _native_reads(skills, limit=1000),
    )
    partial = partial_events[0].skill_load
    full = full_events[0].skill_load
    assert partial is not None and partial.partial and partial.child
    assert full is not None and not full.partial and not full.child
    assert partial.load_id != full.load_id
    assert "lines 1-100 of 222" in str(partial_text[-1].content)
    assert "instruction 217" not in str(partial_text[-1].content)
    assert "lines 1-222 of 222" in str(full_text[-1].content)
    assert "instruction 217" in str(full_text[-1].content)


@pytest.mark.asyncio
@pytest.mark.parametrize("token_limit", [256, 32])
async def test_native_size_clipping_is_partial_despite_requested_1000_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token_limit: int
) -> None:
    original_init = FilesystemMiddleware.__init__

    def small_budget(self, **kwargs):
        original_init(self, **{**kwargs, "tool_token_limit_before_evict": token_limit})

    monkeypatch.setattr(FilesystemMiddleware, "__init__", small_budget)
    skill(tmp_path, body="x" * 4000)
    events, returned = await _native_reads(
        PlatformSkills.from_directory(str(tmp_path)), limit=1000
    )
    assert events[0].skill_load is not None and events[0].skill_load.partial
    assert "truncated" in str(returned[-1].content)
    if token_limit == 32:
        assert "truncated mid-line" in str(returned[-1].content)


def test_legacy_attribution_retains_non_partial_default() -> None:
    load = SkillLoadAttribution.model_validate(
        {
            "name": "example",
            "origin": "agent",
            "revision": "r",
            "load_id": "load",
            "agent_id": "test",
        }
    )
    assert load.partial is False
