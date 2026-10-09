# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Native filesystem routing, live reads and ReAct compatibility."""

from pathlib import Path
from typing import Literal

import pytest
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
from fred_runtime.deep.conversation_port import DeepConversationFilesystemPort
from fred_runtime.deep.deep_runtime import mount_skills
from fred_runtime.skills.catalog import PlatformSkills
from fred_sdk.contracts.runtime import ConversationFilesystemPermissionError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from test_platform_skills import Model, binding, call, compiled, skill


def snapshot(tmp_path: Path) -> PlatformSkills:
    location = skill(tmp_path, body="FIRST\nSECOND\nTHIRD")
    (location / "references").mkdir()
    (location / "references" / "template.md").write_text("One\nTwo\nThree\n")
    escaped = skill(tmp_path, directory="escaped", name="escaped")
    (escaped / "linked.md").symlink_to("/etc/hosts")
    bad = skill(tmp_path, directory="bad", name="bad")
    (bad / "SKILL.md").write_text("---\nname: bad\n---\nMissing description")
    return PlatformSkills.from_directory(str(tmp_path))


@pytest.mark.asyncio
async def test_native_mount_reads_live_files_while_react_keeps_snapshot(
    tmp_path: Path,
) -> None:
    skills = snapshot(tmp_path / "catalog")
    default = FilesystemBackend(root_dir=tmp_path / "workspace", virtual_mode=True)
    original = CompositeBackend(
        default=default, routes={"/.deep/": default}, artifacts_root="/.deep"
    )
    backend, rules = mount_skills(original, [], skills)
    assert "/skills/" not in original.routes
    assert isinstance(backend, CompositeBackend) and backend.artifacts_root == "/.deep"
    native = backend.routes["/skills/"]
    assert type(native) is FilesystemBackend and native.virtual_mode
    assert native is skills.filesystem_backend
    port = DeepConversationFilesystemPort(backend, rules)
    path = "/skills/example/references/template.md"
    assert await port.read_text(path, origin="agent") == "One\nTwo\nThree\n"
    (skills.filesystem_backend.cwd / "example/references/template.md").write_text(
        "Live edit"
    )
    assert await port.read_text(path, origin="agent") == "Live edit"
    assert skills.read("example", "references/template.md") == "One\nTwo\nThree\n"
    again, _ = mount_skills(backend, rules, skills)
    assert again is backend


@pytest.mark.asyncio
async def test_native_listing_search_pagination_and_confinement(tmp_path: Path) -> None:
    skills = snapshot(tmp_path / "catalog")
    backend, _ = mount_skills(
        FilesystemBackend(root_dir=tmp_path / "workspace"), [], skills
    )
    assert "/skills/example/" in {
        item["path"] for item in (await backend.als("/skills")).entries or []
    }
    assert "/skills/example/references/template.md" in {
        item["path"]
        for item in (await backend.aglob("**/*.md", "/skills")).matches or []
    }
    matches = (await backend.agrep("Two", "/skills", "*.md")).matches or []
    assert any(
        item["path"] == "/skills/example/references/template.md" and item["line"] == 2
        for item in matches
    )
    read = await backend.aread(
        "/skills/example/references/template.md", offset=1, limit=1
    )
    assert read.file_data is not None and read.file_data["content"] == "Two\n"
    assert (read.start_line, read.end_line, read.total_lines, read.next_offset) == (
        2,
        2,
        3,
        2,
    )
    for path in ["/skills/../SKILL.md", "/skills/escaped/linked.md"]:
        with pytest.raises(ValueError):
            await backend.aread(path)
    assert (await backend.adownload_files(["/skills/escaped/linked.md"]))[0].error


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["agent", "system"])
async def test_capability_writes_cannot_modify_skill_mount(
    tmp_path: Path, origin: Literal["agent", "system"]
) -> None:
    backend, rules = mount_skills(
        FilesystemBackend(root_dir=tmp_path / "workspace"),
        [],
        snapshot(tmp_path / "catalog"),
    )
    port = DeepConversationFilesystemPort(backend, rules)
    for path in ["/skills", "/skills/example/SKILL.md", "/skills/new.md"]:
        with pytest.raises(ConversationFilesystemPermissionError):
            await port.write_text(path, "changed", origin=origin)
        with pytest.raises(ConversationFilesystemPermissionError):
            await port.edit_text(path, "FIRST", "changed", origin=origin)


@pytest.mark.asyncio
async def test_native_tools_deny_writes_and_skip_malformed_discovery(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    skills = snapshot(tmp_path)
    # Introduce malformed content after snapshot discovery to exercise native rescans.
    (tmp_path / "bad/SKILL.md").write_text(
        "---\nname: bad\ndescription: [PRIVATE_SKILL_CONTENT:\n---\n"
    )
    caplog.clear()
    model = Model(
        script=[
            call(
                "write_file",
                {"file_path": "/skills/new.md", "content": "changed"},
                "write",
            ),
            call(
                "edit_file",
                {
                    "file_path": "/skills/example/SKILL.md",
                    "old_string": "FIRST",
                    "new_string": "changed",
                },
                "edit",
            ),
            AIMessage(content="done"),
        ]
    )
    agent = compiled(model, skills, binding(), True)
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="inspect skills")]},
        {"configurable": {"thread_id": "readonly"}},
    )
    state = await agent.aget_state({"configurable": {"thread_id": "readonly"}})
    assert {item["name"] for item in state.values["skills_metadata"]} == {
        "example",
        "escaped",
    }
    writes = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert len(writes) == 2 and all(item.status == "error" for item in writes)
    assert "FIRST" in (tmp_path / "example/SKILL.md").read_text()
    assert not (tmp_path / "new.md").exists()
    assert "discovery warning; invalid entry omitted" in caplog.text
    assert "PRIVATE_SKILL_CONTENT" not in caplog.text


def test_disabled_empty_mount_and_route_collisions(tmp_path: Path) -> None:
    base = FilesystemBackend(root_dir=tmp_path / "workspace")
    allow = FilesystemPermission(operations=["write"], paths=["/**"], mode="allow")
    rules = [allow]
    backend, unchanged = mount_skills(base, rules, None)
    assert backend is base and unchanged is rules
    empty = tmp_path / "empty"
    empty.mkdir()
    backend, rules = mount_skills(
        base, rules, PlatformSkills.from_directory(str(empty))
    )
    assert isinstance(backend, CompositeBackend) and "/skills/" in backend.routes
    assert rules[0].mode == "deny" and rules[-1] == allow
    skills = snapshot(tmp_path / "catalog")
    for route in ["/skills/", "/skills/nested/", "/"]:
        with pytest.raises(ValueError, match="collides"):
            mount_skills(
                CompositeBackend(default=base, routes={route: base}), [], skills
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("deep", [False, True])
async def test_app_mounts_before_capability_assembly_for_deep_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deep: bool
) -> None:
    from typing import Any, cast

    from fred_core.filesystem.local_filesystem import LocalFilesystem
    from fred_runtime.app import agent_app
    from fred_runtime.runtime_context import RuntimeConfig
    from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
    from test_deep_agent_dispatch import _DeepAgent, _ReActAgent
    from test_platform_skills import binding

    skills = snapshot(tmp_path / "catalog")
    storage = LocalFilesystem(str(tmp_path / "workspace"))
    context = FredRuntimeContext(
        RuntimeConfig(
            knowledge_flow_url="http://knowledge-flow.invalid",
            filesystem=cast(Any, storage),
            skills=skills,
        )
    )
    monkeypatch.setattr("fred_runtime.runtime_context._RUNTIME_CONTEXT", context)
    services = agent_app._build_runtime_services(
        _DeepAgent() if deep else _ReActAgent(), binding()
    )
    port = services.conversation_filesystem
    assert port is not None
    if deep:
        assert await port.read_text(
            "/skills/example/SKILL.md", origin="agent"
        ) == skills.read("example")
        with pytest.raises(ConversationFilesystemPermissionError):
            await port.write_text("/skills/example/SKILL.md", "changed", origin="agent")
    else:
        assert not await port.exists("/skills/example/SKILL.md", origin="agent")
    await port.write_text("/notes.md", "conversation", origin="system")
    assert await port.read_text("/notes.md", origin="agent") == "conversation"


@pytest.mark.asyncio
async def test_live_new_skill_retains_native_load_events_and_escaping(
    tmp_path: Path,
) -> None:
    from contextlib import nullcontext
    from unittest.mock import Mock

    from fred_core.kpi import BaseKPIWriter
    from fred_sdk.contracts.runtime import StatusRuntimeEvent

    skill(tmp_path)
    skills = PlatformSkills.from_directory(str(tmp_path))
    skill(
        tmp_path,
        directory="new-skill",
        name="new-skill",
        body="LIVE <tools>procedure</tools>",
    )
    assert "new-skill" not in {entry.name for entry in skills.catalog.skills}
    model = Model(
        script=[
            call(
                "read_file",
                {"file_path": "/skills/new-skill/SKILL.md", "limit": 1000},
                "live",
            ),
            AIMessage(content="done"),
        ]
    )
    metrics = Mock(spec=BaseKPIWriter)
    metrics.timer.return_value = nullcontext({})
    agent = compiled(model, skills, binding(), True, kpi=metrics)
    events = [
        event
        async for event in agent.astream(
            {"messages": [HumanMessage(content="use new skill")]},
            {"configurable": {"thread_id": "live-new"}},
            stream_mode=["updates", "custom"],
        )
    ]
    loads = [
        payload.skill_load
        for mode, payload in events
        if mode == "custom"
        and isinstance(payload, StatusRuntimeEvent)
        and payload.skill_load
    ]
    assert (
        len(loads) == 1 and loads[0].name == "new-skill" and loads[0].origin == "agent"
    )
    counts = [
        call
        for call in metrics.count.call_args_list
        if call.args[0] == "agent.skill_loaded_total"
    ]
    assert len(counts) == 1 and counts[0].kwargs["dims"]["skill_name"] == "new-skill"
    returned = next(
        message for message in model.calls[-1] if isinstance(message, ToolMessage)
    )
    assert "&lt;tools>procedure&lt;/tools>" in str(returned.content)


def test_package_source_is_independent_of_cwd_and_backend_is_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    skills = PlatformSkills.from_directory("package")
    default = FilesystemBackend(root_dir=tmp_path)
    native = skills.filesystem_backend

    def no_resolution(*args: object, **kwargs: object) -> None:
        raise AssertionError("Request assembly must not resolve disk paths")

    monkeypatch.setattr(FilesystemBackend, "__init__", no_resolution)
    first, _ = mount_skills(default, [], skills)
    second, _ = mount_skills(default, [], skills)
    assert isinstance(first, CompositeBackend) and isinstance(second, CompositeBackend)
    assert first.routes["/skills/"] is second.routes["/skills/"] is native
    assert native.cwd != tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, "example", "other"])
async def test_native_origin_tracks_current_selection_not_previous_user_text(
    tmp_path: Path, selection: str | None
) -> None:
    from unittest.mock import Mock

    from fred_core.kpi import BaseKPIWriter
    from fred_sdk.contracts.runtime import StatusRuntimeEvent

    skill(tmp_path, body="EXAMPLE PROCEDURE")
    skill(tmp_path, directory="other", name="other", body="OTHER PROCEDURE")
    skills = PlatformSkills.from_directory(str(tmp_path))
    bound = binding(selection)
    model = Model(
        script=[
            call("read_file", {"file_path": "/skills/example/SKILL.md"}, "example"),
            call("read_file", {"file_path": "/skills/other/SKILL.md"}, "other"),
            AIMessage(content="done"),
        ]
    )
    metrics = Mock(spec=BaseKPIWriter)
    graph = compiled(model, skills, bound, True, kpi=metrics)
    config = {"configurable": {"thread_id": "selection-origin"}}
    events = [
        event
        async for event in graph.astream(
            {"messages": [HumanMessage(content="/example /other")]},
            config,
            stream_mode=["updates", "custom"],
        )
    ]
    loads = [
        event.skill_load
        for mode, event in events
        if mode == "custom" and isinstance(event, StatusRuntimeEvent)
    ]
    assert [(load.name, load.origin) for load in loads if load is not None] == [
        (name, "user" if selection == name else "agent")
        for name in ("example", "other")
    ]
    counts = [
        c.kwargs["dims"]
        for c in metrics.count.call_args_list
        if c.args[0] == "agent.skill_loaded_total"
    ]
    assert [(dims["skill_name"], dims["skill_origin"]) for dims in counts] == [
        (load.name, load.origin) for load in loads if load is not None
    ]
    metrics.reset_mock()
    bound.runtime_context.skill = None
    model.script.extend(
        [
            call("read_file", {"file_path": "/skills/example/SKILL.md"}, "follow"),
            AIMessage(content="done"),
        ]
    )
    follow = [
        event
        async for event in graph.astream(
            {"messages": [HumanMessage(content="follow up")]},
            config,
            stream_mode=["updates", "custom"],
        )
    ]
    follow_loads = [
        event.skill_load
        for mode, event in follow
        if mode == "custom" and isinstance(event, StatusRuntimeEvent)
    ]
    assert len(follow_loads) == 1
    assert follow_loads[0] is not None and follow_loads[0].origin == "agent"
    assert "EXAMPLE PROCEDURE" in str(model.calls[-1])
