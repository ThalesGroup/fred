import pytest
from fred_core import (
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


def _user() -> KeycloakUser:
    """Return one user for isolated scoped-area filesystem tests."""

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

    async def get_bytes(self, *args, **kwargs):
        self.calls.append(("get_bytes", args, kwargs))
        return b"\x89PNG"

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
        self.team_ids: list[str] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        self.checks.append((user, permission, resource_id))

    async def lookup_user_resources(self, user, permission):
        self.lookup_calls.append((user, permission))
        if permission == TeamPermission.CAN_READ:
            return [RebacReference(Resource.TEAM, team_id) for team_id in self.team_ids]
        return []


def _scoped_filesystem() -> tuple[ScopedAreaFilesystem, _ScopedStorageStub, _RebacStub]:
    """Build one team-rooted scoped-area router with storage and rebac stubs."""

    storage = _ScopedStorageStub()
    rebac = _RebacStub()
    return (
        ScopedAreaFilesystem(scoped_storage=storage, rebac=rebac),
        storage,
        rebac,
    )


# ── shared sub-area ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shared_list_routes_to_team_storage():
    scoped_fs, storage, rebac = _scoped_filesystem()

    entries = await scoped_fs.list_area(_user(), ("acme", "shared", "reports"))

    assert [entry.path for entry in entries] == ["notes.txt"]
    # Box-entry gate: membership (CAN_READ) is checked before storage access.
    assert rebac.checks == [(_user(), TeamPermission.CAN_READ, "acme")]
    assert storage.calls == [("list", (_user(), "shared/reports"), {"owner_override": "acme", "root_prefix": "teams"})]


@pytest.mark.asyncio
async def test_shared_read_checks_membership_only():
    scoped_fs, storage, rebac = _scoped_filesystem()

    content = await scoped_fs.cat_area(_user(), ("acme", "shared", "templates", "deck.md"))

    assert content == "hello"
    assert rebac.checks == [(_user(), TeamPermission.CAN_READ, "acme")]
    assert storage.calls == [
        ("get_text", (_user(), "shared/templates/deck.md"), {"owner_override": "acme", "root_prefix": "teams"}),
    ]


@pytest.mark.asyncio
async def test_shared_write_requires_update_resources():
    scoped_fs, storage, rebac = _scoped_filesystem()

    await scoped_fs.write_area(_user(), ("acme", "shared", "outputs", "report.md"), "hello")

    # Membership first (box entry), then the stronger write permission for the shared space.
    assert rebac.checks == [
        (_user(), TeamPermission.CAN_READ, "acme"),
        (_user(), TeamPermission.CAN_UPDATE_RESOURCES, "acme"),
    ]
    assert storage.calls == [
        ("put", (_user(), "shared/outputs/report.md", "hello"), {"owner_override": "acme", "root_prefix": "teams"}),
    ]


# ── personal-in-team (users) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shared_read_bytes_routes_to_storage():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    data = await scoped_fs.read_bytes_area(_user(), ("acme", "shared", "templates", "deck.pptx"))

    assert data == b"\x89PNG"
    assert storage.calls == [
        ("get_bytes", (_user(), "shared/templates/deck.pptx"), {"owner_override": "acme", "root_prefix": "teams"}),
    ]


@pytest.mark.asyncio
async def test_shared_write_bytes_requires_update_resources():
    scoped_fs, storage, rebac = _scoped_filesystem()

    await scoped_fs.write_bytes_area(_user(), ("acme", "shared", "outputs", "deck.pptx"), b"\x00\x01")

    assert rebac.checks == [
        (_user(), TeamPermission.CAN_READ, "acme"),
        (_user(), TeamPermission.CAN_UPDATE_RESOURCES, "acme"),
    ]
    assert storage.calls == [
        ("put", (_user(), "shared/outputs/deck.pptx", b"\x00\x01"), {"owner_override": "acme", "root_prefix": "teams"}),
    ]


@pytest.mark.asyncio
async def test_write_bytes_rejects_other_uid():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    with pytest.raises(PermissionError, match="another user's personal space"):
        await scoped_fs.write_bytes_area(_user(), ("acme", "users", "someone-else", "x.pptx"), b"\x00")

    assert storage.calls == []


@pytest.mark.asyncio
async def test_users_area_allows_own_uid():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    content = await scoped_fs.cat_area(_user(), ("acme", "users", "u-1", "note.md"))

    assert content == "hello"
    assert storage.calls == [
        ("get_text", (_user(), "users/u-1/note.md"), {"owner_override": "acme", "root_prefix": "teams"}),
    ]


@pytest.mark.asyncio
async def test_users_area_rejects_other_uid():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    with pytest.raises(PermissionError, match="another user's personal space"):
        await scoped_fs.cat_area(_user(), ("acme", "users", "someone-else", "note.md"))

    # Ownership is enforced before any storage access.
    assert storage.calls == []


@pytest.mark.asyncio
async def test_users_root_lists_only_own_uid():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    entries = await scoped_fs.list_area(_user(), ("acme", "users"))

    assert [entry.path for entry in entries] == ["u-1"]


# ── agent-per-user (agents) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_user_path_routes_to_storage():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    await scoped_fs.write_area(_user(), ("acme", "agents", "slide-builder", "users", "u-1", "draft.pptx"), "x")

    assert storage.calls == [
        (
            "put",
            (_user(), "agents/slide-builder/users/u-1/draft.pptx", "x"),
            {"owner_override": "acme", "root_prefix": "teams"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_user_path_requires_users_segment():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    with pytest.raises(FileNotFoundError, match="Agent path must be"):
        await scoped_fs.cat_area(_user(), ("acme", "agents", "slide-builder", "draft.pptx"))


# ── grep, roots, malformed ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grep_returns_team_visible_absolute_paths():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    matches = await scoped_fs.grep_area(_user(), "todo", ("acme", "shared", "notes"))

    assert matches == ["/teams/acme/notes.txt"]
    assert storage.calls[-1] == (
        "grep",
        (_user(), "todo", "shared/notes"),
        {"owner_override": "acme", "root_prefix": "teams"},
    )


@pytest.mark.asyncio
async def test_teams_root_lists_only_readable_team_ids():
    scoped_fs, _storage, rebac = _scoped_filesystem()
    rebac.team_ids = ["team-2", "team-1"]

    entries = await scoped_fs.list_area(_user(), ())

    assert [entry.path for entry in entries] == ["team-1", "team-2"]
    assert rebac.lookup_calls == [(_user(), TeamPermission.CAN_READ)]


@pytest.mark.asyncio
async def test_team_box_lists_subareas():
    scoped_fs, _storage, rebac = _scoped_filesystem()

    entries = await scoped_fs.list_area(_user(), ("acme",))

    assert [entry.path for entry in entries] == ["users", "shared", "agents"]
    assert rebac.checks == [(_user(), TeamPermission.CAN_READ, "acme")]


@pytest.mark.asyncio
async def test_rejects_unsupported_sub_area():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    with pytest.raises(FileNotFoundError, match="Unsupported team sub-area"):
        await scoped_fs.cat_area(_user(), ("acme", "bogus", "x"))
