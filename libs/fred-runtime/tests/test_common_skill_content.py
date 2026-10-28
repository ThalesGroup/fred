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
from fred_sdk.contracts.runtime import ExecutionConfig, RuntimeServices
from langchain_core.messages import AIMessage, ToolMessage
from test_platform_skills import Model, binding, call, compiled

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


def test_packaged_data_analysis_is_available_to_users_and_agents() -> None:
    """The common analysis procedure works through either invocation route."""
    skills = PlatformSkills.from_directory("package")
    analysis = next(
        (s for s in skills.catalog.skills if s.name == "analyze-data"), None
    )
    assert analysis is not None
    assert analysis.builtin and analysis.user_invocable
    assert not analysis.disable_model_invocation
    assert skills.for_execution().read("analyze-data")
    assert skills.for_execution(("analyze-data",)).read("analyze-data")


def test_packaged_visualization_is_agent_only_and_obeys_global_disablement() -> None:
    """An agent can read visualization guidance; users cannot force it directly."""
    skills = PlatformSkills.from_directory("package")
    visualization = next(
        (s for s in skills.catalog.skills if s.name == "data-visualization"), None
    )
    assert visualization is not None
    assert visualization.builtin and not visualization.user_invocable
    assert not visualization.disable_model_invocation
    assert skills.for_execution().read("data-visualization")
    with pytest.raises(ValueError, match="user-invocable"):
        skills.for_execution(("data-visualization",))
    with pytest.raises(ValueError):
        skills.for_execution(disabled_names=("data-visualization",)).read(
            "data-visualization"
        )


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
        (
            "analyze-data",
            "Groups: A has 90 successes in 100 attempts; B has 1 in 10. "
            "What is the overall success rate, and did A's process cause it?",
        ),
        (
            "analyze-data",
            "Analyze the spreadsheet I mentioned. No file or values are attached. "
            "Give an exact result.",
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
async def test_agent_can_load_packaged_visualization_for_a_chart_request() -> None:
    """The agent-only procedure reaches the compiled tool loop as instructions."""
    skills = PlatformSkills.from_directory("package").for_execution()
    model = Model(
        script=[
            call("load_skill", {"name": "data-visualization"}, "visualization"),
            AIMessage(content="comparison probe"),
        ]
    )
    agent = compiled(model, skills, binding(), False)
    await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Show A=10 and B=20 clearly."}]},
        {"configurable": {"thread_id": "visualization"}},
    )
    loaded = [
        message
        for message in model.calls[-1]
        if isinstance(message, ToolMessage) and message.tool_call_id == "visualization"
    ]
    assert len(loaded) == 1
    assert skills.read("data-visualization") in str(loaded[0].content)
    assert "data-visualization" not in model.bound_tool_names
