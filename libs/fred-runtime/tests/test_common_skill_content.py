# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Packaged procedures, licensing and instruction delivery at public skill seams."""

from __future__ import annotations

import hashlib
import re
from importlib.resources import files

import pytest
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.skills.catalog import PlatformSkills
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    RuntimeServices,
    StatusRuntimeEvent,
)
from langchain_core.messages import AIMessage, ToolMessage
from test_platform_skills import Model, binding, call, compiled, load_call

UPSTREAM_REVISION = "59db609eb1e18aaf59b63284d0e52255aff0c63c"  # pragma: allowlist secret - public source commit


def test_packaged_interview_preserves_explicit_invocation_and_mit_provenance() -> None:
    """Users can select the adapted interview with its distributed license intact."""
    skills = PlatformSkills.from_directory("package")
    interview = next((s for s in skills.catalog.skills if s.name == "grill-me"), None)
    assert interview is not None
    assert interview.builtin and interview.user_invocable
    assert interview.disable_model_invocation
    selected = skills.for_execution(("grill-me",))
    assert selected.read("grill-me", "references/decision-interview.md")
    license_text = selected.read("grill-me", "LICENSE.txt")
    license_bytes = license_text.encode()
    git_blob = f"blob {len(license_bytes)}\0".encode() + license_bytes
    assert (
        hashlib.sha1(git_blob, usedforsecurity=False).hexdigest()
        == (
            "f1dd2c09108dde1a5f56097cee8461b3ea834499"  # pragma: allowlist secret - public license blob
        )
    )
    assert UPSTREAM_REVISION in selected.read("grill-me", "NOTICE.md")
    with pytest.raises(ValueError):
        skills.for_execution().read("grill-me")


@pytest.mark.parametrize(
    "name", ["analyze-data", "compare-options", "summarize-document"]
)
def test_packaged_model_only_skills_obey_user_and_global_eligibility(name: str) -> None:
    """Model-only procedures remain readable while user bypasses are rejected."""
    skills = PlatformSkills.from_directory("package")
    procedure = next(s for s in skills.catalog.skills if s.name == name)
    assert procedure.builtin and not procedure.user_invocable
    assert not procedure.disable_model_invocation
    assert skills.for_execution().read(name)
    with pytest.raises(ValueError, match="user-invocable"):
        skills.for_execution((name,))
    with pytest.raises(ValueError):
        skills.for_execution(disabled_names=(name,)).read(name)


def test_packaged_minutes_require_current_user_selection() -> None:
    """A new autonomous load cannot activate the explicit minutes workflow."""
    skills = PlatformSkills.from_directory("package")
    minutes = next(s for s in skills.catalog.skills if s.name == "meeting-minutes")
    assert minutes.user_invocable and minutes.disable_model_invocation
    with pytest.raises(ValueError, match="unavailable"):
        skills.for_execution().read("meeting-minutes")
    selected = skills.for_execution(("meeting-minutes",))
    assert selected.read("meeting-minutes", "references/meeting-minutes-template.md")
    assert "meeting-minutes" not in skills.for_execution().prompt


@pytest.mark.parametrize("name", ["data-visualization", "verify-answer"])
def test_retired_packaged_names_cannot_start_new_loads_or_selections(name: str) -> None:
    """Retirement does not silently redirect old command identities."""
    skills = PlatformSkills.from_directory("package")
    with pytest.raises(ValueError, match="unavailable"):
        skills.for_execution((name,))
    with pytest.raises(ValueError, match="unavailable"):
        skills.for_execution().read(name)


def test_original_skill_instructions_do_not_require_external_documentation() -> None:
    """Packaged original procedures stay readable without fetching a web page."""
    skills = PlatformSkills.from_directory("package")
    for skill in skills.catalog.skills:
        if skill.name == "grill-me":
            continue  # Imported material retains its upstream references and notices.
        pending = [files("fred_runtime.skills").joinpath(skill.name)]
        while pending:
            resource = pending.pop()
            if resource.is_dir():
                pending.extend(resource.iterdir())
            else:
                assert not re.search(
                    r"https?://|www\.", resource.read_text(encoding="utf-8")
                ), str(resource)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "prompt"),
    [
        (
            "grill-me",
            "Challenge my plan for a weekend workshop with 30 volunteers.",
        ),
    ],
)
async def test_representative_requests_receive_selected_instructions_without_input_rewrite(
    name: str, prompt: str
) -> None:
    """Compare instruction transport, without claiming scripted-model quality gains."""
    packaged = PlatformSkills.from_directory("package")
    procedure = packaged.read(name)
    for selected in (False, True):
        skills = packaged.for_execution((name,)) if selected else PlatformSkills({})
        bound = binding(name if selected else None)
        model = Model(script=[AIMessage(content="comparison probe")])
        graph = compiled(model, skills, bound, False)
        executor = _TransportBackedReActExecutor(
            compiled_agent=graph,
            binding=bound,
            services=RuntimeServices(skills=skills),
            runtime_class_name="ReActRuntime",
        )
        result = await executor.invoke(
            ReActInput(
                messages=(ReActMessage(role=ReActMessageRole.USER, content=prompt),)
            ),
            ExecutionConfig(session_id="session"),
        )
        assert result.final_message.content == "comparison probe"
        first_messages = model.calls[0]
        assert first_messages[-1].content == prompt
        assert any(procedure in str(message.content) for message in first_messages) == (
            selected
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("deep", [False, True])
@pytest.mark.parametrize("name", ["analyze-data", "compare-options", "graph"])
async def test_agent_can_load_packaged_workflows_without_user_selection(
    name: str,
    deep: bool,
) -> None:
    """Natural requests can load procedures without exposing extra tools."""
    skills = PlatformSkills.from_directory("package").for_execution()
    model = Model(
        script=[
            load_call(name, "procedure", deep),
            AIMessage(content="comparison probe"),
        ]
    )
    agent = compiled(model, skills, binding(), deep)
    await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Show A=10 and B=20 clearly."}]},
        {"configurable": {"thread_id": "visualization"}},
    )
    loaded = [
        message
        for message in model.calls[-1]
        if isinstance(message, ToolMessage) and message.tool_call_id == "procedure"
    ]
    assert len(loaded) == 1
    assert all(
        line in str(loaded[0].content)
        for line in skills.read(name).splitlines()
        if line.strip()
    )
    assert "flowchart TD" not in str(model.calls[-1])
    assert name not in model.bound_tool_names


@pytest.mark.asyncio
@pytest.mark.parametrize("child", [False, True])
async def test_native_minutes_cannot_be_loaded_without_explicit_user_selection(
    child: bool,
) -> None:
    """Packaged user-only eligibility reaches parent and child filesystem reads."""
    script = [
        load_call("meeting-minutes", "denied-load", True),
        AIMessage(content="done"),
    ]
    if child:
        script = [
            call(
                "task",
                {
                    "description": "Read the minutes method",
                    "subagent_type": "general-purpose",
                },
                "child",
            ),
            *script,
            AIMessage(content="parent done"),
        ]
    model = Model(script=script)
    agent = compiled(model, PlatformSkills.from_directory("package"), binding(), True)
    events = [
        event
        async for event in agent.astream(
            {
                "messages": [
                    {"role": "user", "content": "Inspect the available methods."}
                ]
            },
            {"configurable": {"thread_id": f"denied-minutes-{child}"}},
            stream_mode=["updates", "custom"],
            subgraphs=True,
        )
    ]
    assert not [
        payload
        for _, mode, payload in events
        if mode == "custom"
        and isinstance(payload, StatusRuntimeEvent)
        and payload.skill_load
    ]
    attempted = [
        m
        for messages in model.calls
        for m in messages
        if isinstance(m, ToolMessage) and m.tool_call_id == "denied-load"
    ]
    assert attempted
    assert all(
        any(word in str(m.content).lower() for word in ["error", "denied", "not found"])
        for m in attempted
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("deep", [False, True])
@pytest.mark.parametrize(
    ("name", "path", "marker"),
    [
        ("graph", "references/mermaid.md", "flowchart TD"),
        (
            "summarize-document",
            "references/complex-summaries.md",
            "apparent disagreement",
        ),
    ],
)
async def test_conditional_references_reach_the_model_only_after_a_reference_read(
    deep: bool, name: str, path: str, marker: str
) -> None:
    """Packaged references use the real compiled ReAct and native Deep readers."""
    skills = PlatformSkills.from_directory("package").for_execution()
    model = Model(
        script=[
            load_call(name, "procedure", deep),
            call(
                "read_file" if deep else "read_skill_file",
                {"file_path": f"/skills/{name}/{path}", "limit": 1000}
                if deep
                else {"name": name, "path": path},
                "reference",
            ),
            AIMessage(content="done"),
        ]
    )
    agent = compiled(model, skills, binding(), deep)
    await agent.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "Use the relevant detailed method."}
            ]
        },
        {"configurable": {"thread_id": f"reference-{name}-{deep}"}},
    )
    assert marker not in str(model.calls[0])
    assert marker not in str(model.calls[1])
    references = [
        m
        for m in model.calls[-1]
        if isinstance(m, ToolMessage) and m.tool_call_id == "reference"
    ]
    assert len(references) == 1 and marker in str(references[0].content)
