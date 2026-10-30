# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Native filesystem routing, live reads and ReAct compatibility."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast

import pytest
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission
from fred_runtime.deep.concat_files import ConcatFilesMiddleware
from fred_runtime.deep.conversation_port import DeepConversationFilesystemPort
from fred_runtime.deep.deep_runtime import mount_skills
from fred_runtime.skills.catalog import PlatformSkills
from fred_sdk.contracts.runtime import (
    ConversationFilesystemInterruptError,
    ConversationFilesystemPermissionError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadStorageError,
)
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


def alias_port(tmp_path: Path) -> DeepConversationFilesystemPort:
    root = tmp_path / "catalog"
    hidden = skill(root, directory="hidden", name="hidden")
    (hidden / "SKILL.md").write_text(
        "---\nname: hidden\ndescription: Hidden procedure\n"
        "disable-model-invocation: true\n---\nHIDDEN BODY"
    )
    visible = skill(root, directory="visible", name="visible", body="VISIBLE BODY")
    (visible / "alias.py").symlink_to("../hidden/SKILL.md")
    (visible / "allowed.py").symlink_to("SKILL.md")
    (visible / "missing.py").symlink_to("missing.txt")
    (tmp_path / "outside.txt").write_text("OUTSIDE BODY")
    (visible / "escape.py").symlink_to("../../outside.txt")
    skills = PlatformSkills.from_directory(str(root)).for_execution()
    assert [entry.name for entry in skills.catalog.skills] == ["visible"]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    backend, rules = mount_skills(
        FilesystemBackend(root_dir=workspace, virtual_mode=True), [], skills
    )
    return DeepConversationFilesystemPort(backend, rules)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["agent", "system"])
async def test_capability_alias_cannot_read_ineligible_skill(
    tmp_path: Path, origin: Literal["agent", "system"]
) -> None:
    port = alias_port(tmp_path)
    with pytest.raises(ConversationFilesystemPermissionError):
        await port.read_text("/skills/visible/alias.py", origin=origin)


@pytest.mark.asyncio
async def test_concat_cannot_copy_ineligible_skill_through_alias(
    tmp_path: Path,
) -> None:
    port = alias_port(tmp_path)
    concat = ConcatFilesMiddleware(port).tools[0]
    result = await concat.ainvoke(
        {"paths": ["/skills/visible/alias.py"], "output_path": "/copied.md"}
    )
    assert "Permission denied" in str(result)
    assert "HIDDEN BODY" not in str(result)
    assert not await port.exists("/copied.md", origin="agent")


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["alias.py", "allowed.py", "missing.py", "escape.py"])
async def test_native_and_capability_alias_reads_share_target_semantics(
    tmp_path: Path, alias: str
) -> None:
    port = alias_port(tmp_path)
    middleware = FilesystemMiddleware(
        backend=port.backend, _permissions=port.permissions
    )
    reader = next(entry for entry in middleware.tools if entry.name == "read_file")
    path = f"/skills/visible/{alias}"
    result = await cast(Any, reader).coroutine(
        file_path=path,
        runtime=cast(Any, SimpleNamespace(tool_call_id="alias-read")),
    )
    assert isinstance(result, ToolMessage)
    if alias == "allowed.py":
        assert result.status == "success"
        assert "VISIBLE BODY" in str(result.content)
        assert "VISIBLE BODY" in await port.read_text(path, origin="agent")
    else:
        assert result.status == "error"
        assert "HIDDEN BODY" not in str(result.content)
        error = {
            "alias.py": ConversationFilesystemPermissionError,
            "missing.py": ConversationScratchpadFileNotFoundError,
            "escape.py": ConversationScratchpadStorageError,
        }[alias]
        with pytest.raises(error):
            await port.read_text(path, origin="agent")


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["agent", "system"])
async def test_capability_permitted_alias_and_missing_file_keep_behavior(
    tmp_path: Path, origin: Literal["agent", "system"]
) -> None:
    port = alias_port(tmp_path)
    expected = await port.read_text("/skills/visible/SKILL.md", origin=origin)
    assert await port.read_text("/skills/visible/allowed.py", origin=origin) == expected
    for path in ("/skills/visible/missing.py", "/skills/visible/absent.txt"):
        with pytest.raises(ConversationScratchpadFileNotFoundError):
            await port.read_text(path, origin=origin)
    concat = ConcatFilesMiddleware(port).tools[0]
    result = await concat.ainvoke(
        {"paths": ["/skills/visible/allowed.py"], "output_path": "/copied.md"}
    )
    assert "Concatenated 1 file(s)" in str(result)
    assert await port.read_text("/copied.md", origin=origin) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["agent", "system"])
@pytest.mark.parametrize("mode", ["allow", "interrupt"])
async def test_capability_alias_applies_ordered_target_permissions(
    tmp_path: Path,
    origin: Literal["agent", "system"],
    mode: Literal["allow", "interrupt"],
) -> None:
    port = alias_port(tmp_path)
    target = "/skills/visible/SKILL.md"
    ordered = DeepConversationFilesystemPort(
        port.backend,
        [
            FilesystemPermission(operations=["read"], paths=[target], mode=mode),
            FilesystemPermission(operations=["read"], paths=[target], mode="deny"),
            *port.permissions,
        ],
    )
    if mode == "interrupt":
        with pytest.raises(ConversationFilesystemInterruptError):
            await ordered.read_text("/skills/visible/allowed.py", origin=origin)
    else:
        assert "VISIBLE BODY" in await ordered.read_text(
            "/skills/visible/allowed.py", origin=origin
        )


@pytest.mark.asyncio
async def test_non_skill_reads_keep_system_bypass_without_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "notes-alias.txt").symlink_to("notes.txt")
    resolver = Mock(side_effect=AssertionError("Non-skill read must not resolve again"))
    monkeypatch.setattr(
        "fred_runtime.deep.conversation_port._resolve_real_path", resolver
    )
    port = DeepConversationFilesystemPort(
        backend,
        [FilesystemPermission(operations=["read"], paths=["/**"], mode="interrupt")],
    )
    assert await port.read_text("/notes.txt", origin="system") == "notes"
    with pytest.raises(ConversationFilesystemInterruptError):
        await port.read_text("/notes.txt", origin="agent")
    permitted = DeepConversationFilesystemPort(backend, [])
    assert await permitted.read_text("/notes-alias.txt", origin="agent") == "notes"
    resolver.assert_not_called()


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
    # Validate malformed metadata at startup, before per-turn policy views.
    (tmp_path / "bad/SKILL.md").write_text(
        "---\nname: bad\ndescription: [PRIVATE_SKILL_CONTENT:\n---\n"
    )
    skills = PlatformSkills.from_directory(str(tmp_path))
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
    }
    writes = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert len(writes) == 2 and all(item.status == "error" for item in writes)
    assert "FIRST" in (tmp_path / "example/SKILL.md").read_text()
    assert not (tmp_path / "new.md").exists()
    assert "invalid entry omitted" in caplog.text
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
async def test_new_skill_requires_discovery_before_native_load_events(
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
    # Body edits remain live, while new names require startup validation so
    # malformed invocation flags cannot bypass the execution policy.
    skills = PlatformSkills.from_directory(str(tmp_path))
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
