# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Offline safety, public-hook integration and compiled-loop skill proofs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from deepagents.backends import StateBackend
from fred_runtime.deep.deep_runtime import (
    _build_deepagent_runtime_middleware,
    _create_compiled_deep_agent,
)
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.react.react_tool_binding import ReActToolBinder
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_runtime.react.react_tool_resolution import ReActRuntimeToolResolver
from fred_runtime.skills.catalog import (
    MAX_FILE_BYTES,
    PlatformSkills,
    SnapshotBackend,
    build_skills_middleware,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    RuntimeServices,
    StatusRuntimeEvent,
)
from fred_sdk.contracts.skills import SkillInvocation
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field, ValidationError


def skill(
    root: Path,
    directory: str = "example",
    name: str = "example",
    body: str = "PROCEDURE",
) -> Path:
    location = root / directory
    location.mkdir(parents=True)
    (location / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill\n---\n{body}\n"
    )
    return location


def binding(selection: str | None = None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="session",
            exchange_id="exchange",
            skill=SkillInvocation(name=selection) if selection else None,
        ),
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor="user",
            tenant="team",
            environment=PortableEnvironment.DEV,
            agent_id="test",
        ),
    )


def test_package_discovery_and_read_only_reference() -> None:
    catalog = PlatformSkills.from_directory("package")
    assert [entry.name for entry in catalog.catalog.skills] == ["compte-rendu"]
    assert "Non précisé" in catalog.read(
        "compte-rendu", "references/modele-compte-rendu.md"
    )
    assert "## Décisions" not in catalog.prompt
    backend = SnapshotBackend({})
    assert backend.write("/file", "text").error
    assert backend.edit("/file", "old", "new").error
    assert backend.upload_files([("/file", b"text")])[0].error == "permission_denied"


def test_snapshot_fixed_until_restart_and_checkpoint_metadata_refresh(
    tmp_path: Path,
) -> None:
    location = skill(tmp_path)
    catalog = PlatformSkills.from_directory(str(tmp_path))
    (location / "SKILL.md").write_text(
        "---\nname: example\ndescription: Changed\n---\nNEW"
    )
    assert "PROCEDURE" in catalog.read("example")
    restarted = PlatformSkills.from_directory(str(tmp_path))
    assert restarted.catalog.revision != catalog.catalog.revision
    assert "NEW" in restarted.read("example")
    middleware = restarted.middleware()
    update = middleware.before_agent({"skills_metadata": [], "messages": []}, None, {})
    assert update["skills_metadata"][0]["description"] == "Changed"


@pytest.mark.parametrize(
    "path",
    [
        "../SKILL.md",
        "/etc/passwd",
        "../../other/secret.md",
        "references\\secret.md",
        "x.py",
        "",
    ],
)
def test_reference_confinement(tmp_path: Path, path: str) -> None:
    skill(tmp_path)
    catalog = PlatformSkills.from_directory(str(tmp_path))
    with pytest.raises(ValueError):
        catalog.read("example", path)


def test_invalid_duplicate_utf8_size_and_symlink_entries_are_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill(tmp_path)
    skill(tmp_path, "duplicate", "example")
    invalid = skill(tmp_path, "invalid", "invalid")
    (invalid / "SKILL.md").write_text(
        "---\nname: [SECRET_BODY:\ndescription: invalid\n---"
    )
    oversized = skill(tmp_path, "oversized", "oversized")
    (oversized / "SKILL.md").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    undecodable = skill(tmp_path, "utf", "utf")
    (undecodable / "SKILL.md").write_bytes(b"\xff")
    escape = skill(tmp_path, "escape", "escape")
    (escape / "secret.md").symlink_to("/etc/hosts")
    catalog = PlatformSkills.from_directory(str(tmp_path))
    assert catalog.catalog.skills == ()
    assert "SECRET_BODY" not in caplog.text
    assert "skipped" in caplog.text


def test_unknown_and_forged_selection() -> None:
    with pytest.raises(ValidationError):
        SkillInvocation.model_validate({"name": "compte-rendu", "body": "forged"})
    with pytest.raises(ValueError):
        PlatformSkills.from_directory("package").read("unknown")


class Model(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "platform-skills-test"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Model:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(messages)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=self.script.pop(0)
                    if self.script
                    else AIMessage(content="done")
                )
            ]
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


def call(name: str, args: dict[str, Any], identity: str) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": identity}]
    )


def compiled(
    model: Model, skills: PlatformSkills, bound: BoundRuntimeContext, deep: bool
) -> Any:
    services = RuntimeServices(skills=skills)
    specs = ReActRuntimeToolResolver(
        declared_tool_refs=(), toolset_key=None, services=services, binding=bound
    ).resolve_tools()
    tools = [
        item.tool
        for item in ReActToolBinder(
            runtime_tools=specs, tracer=None, binding=bound
        ).build_tools()
    ]
    policy = ToolApprovalPolicy()
    if deep:

        def middleware(child: bool = False) -> list[Any]:
            return _build_deepagent_runtime_middleware(
                tracer=None,
                kpi=None,
                binding=bound,
                approval_policy=policy,
                available_tool_names={"load_skill", "read_skill_file"},
                skills=skills,
                child=child,
            )

        return _create_compiled_deep_agent(
            model=model,
            tools=tools,
            system_prompt=skills.prompt,
            checkpointer=InMemorySaver(),
            middleware=middleware(),
            subagent_middleware=middleware(True),
            backend=StateBackend(),
            permissions=[],
        )
    return build_tool_loop_compiled_react_agent(
        model=model,
        tools=tools,
        system_prompt=skills.prompt,
        binding=bound,
        approval_policy=policy,
        checkpointer=InMemorySaver(),
        definition=cast(ReActAgentDefinition, SimpleNamespace(agent_id="test")),
        available_tool_names={"load_skill", "read_skill_file"},
        skills_middleware=build_skills_middleware(skills),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("deep", [False, True])
async def test_compiled_load_reference_and_follow_up(deep: bool) -> None:
    skills = PlatformSkills.from_directory("package")
    model = Model(
        script=[
            call("load_skill", {"name": "compte-rendu"}, "load"),
            call(
                "read_skill_file",
                {"name": "compte-rendu", "path": "references/modele-compte-rendu.md"},
                "reference",
            ),
            AIMessage(content="done"),
        ]
    )
    agent = compiled(model, skills, binding(), deep)
    events = [
        event
        async for event in agent.astream(
            {"messages": [HumanMessage(content="notes")]},
            {"configurable": {"thread_id": "session"}},
            stream_mode=["updates", "custom"],
        )
    ]
    loads = [
        payload
        for mode, payload in events
        if mode == "custom" and isinstance(payload, StatusRuntimeEvent)
    ]
    assert len(loads) == 1
    assert loads[0].skill_load is not None and loads[0].skill_load.origin == "agent"
    assert "Non précisé" in str(model.calls[-1])
    assert any(
        isinstance(message, ToolMessage) and message.tool_call_id == "load"
        for message in model.calls[-1]
    )
    await agent.ainvoke(
        {"messages": [HumanMessage(content="follow up")]},
        {"configurable": {"thread_id": "session"}},
    )
    assert "Non précisé" in str(model.calls[-1])


@pytest.mark.asyncio
async def test_manual_preload_before_first_inference_and_missing_selection() -> None:
    skills = PlatformSkills.from_directory("package")
    bound = binding("compte-rendu")
    model = Model()
    graph = compiled(model, skills, bound, False)
    executor = _TransportBackedReActExecutor(
        compiled_agent=graph,
        binding=bound,
        services=RuntimeServices(skills=skills),
        runtime_class_name="ReActRuntime",
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="notes"),)
    )
    config = ExecutionConfig(session_id="session")
    events = [event async for event in executor.stream(input_model, config)]
    assert isinstance(events[0], StatusRuntimeEvent)
    assert events[0].skill_load is not None and events[0].skill_load.origin == "user"
    assert "Ne pas" in str(model.calls[0])
    assert model.calls[0][-1].content == "notes"
    bound.runtime_context.skill = SkillInvocation(name="missing")
    before = len(model.calls)
    with pytest.raises(ValueError):
        await executor.invoke(input_model, config)
    assert len(model.calls) == before


@pytest.mark.asyncio
async def test_native_child_load_has_attribution() -> None:
    skills = PlatformSkills.from_directory("package")
    model = Model(
        script=[
            call(
                "task",
                {"description": "Write minutes", "subagent_type": "general-purpose"},
                "delegate",
            ),
            call("load_skill", {"name": "compte-rendu"}, "child-load"),
            AIMessage(content="child done"),
            AIMessage(content="done"),
        ]
    )
    agent = compiled(model, skills, binding(), True)
    events = [
        event
        async for event in agent.astream(
            {"messages": [HumanMessage(content="notes")]},
            {"configurable": {"thread_id": "session"}},
            stream_mode=["updates", "custom"],
            subgraphs=True,
        )
    ]
    loads = [
        payload.skill_load
        for _, mode, payload in events
        if mode == "custom" and isinstance(payload, StatusRuntimeEvent)
    ]
    assert len(loads) == 1, (str(events), str(model.calls))
    assert loads[0] is not None
    assert loads[0].child is True and loads[0].agent_id == "general-purpose"
