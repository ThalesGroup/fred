import pytest
from fred_core import (
    AgentPermission,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
    KeycloakUser,
    RebacReference,
    Resource,
    TeamPermission,
)

from knowledge_flow_backend.features.filesystem.scoped_area_filesystem import (
    ScopedAreaFilesystem,
)
from knowledge_flow_backend.features.filesystem.virtual_fs_contract import VirtualArea


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated scoped-area filesystem tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
        groups=["admins"],
    )


def _file(path: str) -> FilesystemResourceInfoResult:
    """Build one simple file entry for fake storage responses."""

    return FilesystemResourceInfoResult(
        path=path,
        size=1,
        type=FilesystemResourceInfo.FILE,
        modified=None,
    )


class _ScopedStorageStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list(self, *args, **kwargs):
        self.calls.append(("list", args, kwargs))
        return [_file("notes.txt")]

    async def stat(self, *args, **kwargs):
        self.calls.append(("stat", args, kwargs))
        return _file("notes.txt")

    async def get_text(self, *args, **kwargs):
        self.calls.append(("get_text", args, kwargs))
        return "hello"

    async def put(self, *args, **kwargs):
        self.calls.append(("put", args, kwargs))

    async def delete(self, *args, **kwargs):
        self.calls.append(("delete", args, kwargs))

    async def grep(self, *args, **kwargs):
        self.calls.append(("grep", args, kwargs))
        return ["notes.txt"]

    async def mkdir(self, *args, **kwargs):
        self.calls.append(("mkdir", args, kwargs))


class _RebacStub:
    def __init__(self) -> None:
        self.checks: list[tuple[KeycloakUser, object, str]] = []
        self.lookup_calls: list[tuple[KeycloakUser, object]] = []
        self.agent_ids: list[str] = []
        self.team_ids: list[str] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        self.checks.append((user, permission, resource_id))

    async def lookup_user_resources(self, user, permission):
        self.lookup_calls.append((user, permission))
        if permission == AgentPermission.READ:
            return [RebacReference(Resource.AGENT, agent_id) for agent_id in self.agent_ids]
        if permission == TeamPermission.CAN_READ:
            return [RebacReference(Resource.TEAM, team_id) for team_id in self.team_ids]
        return []


def _scoped_filesystem() -> tuple[ScopedAreaFilesystem, _ScopedStorageStub, _RebacStub]:
    """
    Build one scoped-area router with explicit storage and rebac stubs.

    Why this exists:
    - scoped-area tests should verify routing and permissions without touching real storage
    - returning the stubs lets each test assert the exact delegated call

    How to use:
    - call once per test and inspect the returned stubs after the action

    Example:
    - `scoped_fs, storage, rebac = _scoped_filesystem()`
    """

    storage = _ScopedStorageStub()
    rebac = _RebacStub()
    return (
        ScopedAreaFilesystem(scoped_storage=storage, rebac=rebac),
        storage,
        rebac,
    )


@pytest.mark.asyncio
async def test_workspace_list_routes_directly_to_storage():
    scoped_fs, storage, rebac = _scoped_filesystem()

    entries = await scoped_fs.list_area(_user(), VirtualArea.WORKSPACE, ("reports",))

    assert [entry.path for entry in entries] == ["notes.txt"]
    assert rebac.checks == []
    assert storage.calls == [("list", (_user(), "reports"), {"owner_override": None, "root_prefix": None})]


@pytest.mark.asyncio
async def test_agent_read_checks_permission_and_uses_agent_storage_namespace():
    scoped_fs, storage, rebac = _scoped_filesystem()

    content = await scoped_fs.cat_area(
        _user(),
        VirtualArea.AGENT,
        ("agent-1", "config.yaml"),
    )

    assert content == "hello"
    assert rebac.checks == [(_user(), AgentPermission.READ, "agent-1")]
    assert storage.calls == [
        (
            "get_text",
            (_user(), "config.yaml"),
            {"owner_override": "agent-1/config", "root_prefix": "agents"},
        )
    ]


@pytest.mark.asyncio
async def test_team_write_rejects_team_root():
    scoped_fs, _storage, rebac = _scoped_filesystem()

    with pytest.raises(PermissionError, match="Cannot write to /team/team-1 root"):
        await scoped_fs.write_area(_user(), VirtualArea.TEAM, ("team-1",), "hello")

    assert rebac.checks == [(_user(), TeamPermission.CAN_UPDATE_RESOURCES, "team-1")]


@pytest.mark.asyncio
async def test_grep_returns_visible_absolute_paths():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    matches = await scoped_fs.grep_area(
        _user(),
        VirtualArea.WORKSPACE,
        "todo",
        ("notes",),
    )

    assert matches == ["/workspace/notes.txt"]
    assert storage.calls[-1] == (
        "grep",
        (_user(), "todo", "notes"),
        {"owner_override": None, "root_prefix": None},
    )


@pytest.mark.asyncio
async def test_root_stat_returns_virtual_directory_for_agent_area():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    result = await scoped_fs.stat_area(_user(), VirtualArea.AGENT, ())

    assert result.is_dir()
    assert result.path == "agent"


@pytest.mark.asyncio
async def test_agent_root_lists_only_readable_agent_ids():
    scoped_fs, _storage, rebac = _scoped_filesystem()
    rebac.agent_ids = ["agent-b", "agent-a"]

    entries = await scoped_fs.list_area(_user(), VirtualArea.AGENT, ())

    assert [entry.path for entry in entries] == ["agent-a", "agent-b"]
    assert rebac.lookup_calls == [(_user(), AgentPermission.READ)]


@pytest.mark.asyncio
async def test_team_root_lists_only_readable_team_ids():
    scoped_fs, _storage, rebac = _scoped_filesystem()
    rebac.team_ids = ["team-2", "team-1"]

    entries = await scoped_fs.list_area(_user(), VirtualArea.TEAM, ())

    assert [entry.path for entry in entries] == ["team-1", "team-2"]
    assert rebac.lookup_calls == [(_user(), TeamPermission.CAN_READ)]


@pytest.mark.asyncio
async def test_rejects_unsupported_area():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    with pytest.raises(FileNotFoundError, match="Unsupported filesystem area"):
        await scoped_fs.list_area(_user(), VirtualArea.CORPUS, ())
