# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
        if permission == TeamPermission.CAN_ACCESS_FILES:
            return [RebacReference(Resource.TEAM, team_id) for team_id in self.team_ids]
        return []


class _DenyUpdateRebac(_RebacStub):
    """Grants CAN_ACCESS_FILES (box entry) but denies CAN_UPDATE_RESOURCES (write gate)."""

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        if permission == TeamPermission.CAN_UPDATE_RESOURCES:
            raise PermissionError("update denied")
        await super().check_user_permission_or_raise(user, permission, resource_id)


class _PublicOnlyRebac(_RebacStub):
    """A non-member who only sees the team through marketplace `public` visibility.

    Mirrors schema.fga: `can_read` admits `public`, `can_access_files` does not.
    """

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        if permission != TeamPermission.CAN_READ:
            raise PermissionError(f"{permission.value} denied")
        await super().check_user_permission_or_raise(user, permission, resource_id)

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


# The retired team-shared area must never reach storage.
@pytest.mark.asyncio
async def test_shared_area_is_rejected_before_storage():
    scoped_fs, storage, _rebac = _scoped_filesystem()
    with pytest.raises(FileNotFoundError, match="Unsupported team sub-area"):
        await scoped_fs.read_bytes_area(_user(), ("acme", "shared", "deck.pptx"))
    assert storage.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,args",
    [
        ("list_area", ()),
        ("stat_area", ()),
        ("cat_area", ()),
        ("read_bytes_area", ()),
        ("write_bytes_area", (b"bytes",)),
        ("delete_area", ()),
    ],
)
@pytest.mark.asyncio
async def test_retired_personal_area_rejects_operations(operation, args):
    scoped_fs, storage, _rebac = _scoped_filesystem()

    with pytest.raises(FileNotFoundError, match="Unsupported team sub-area"):
        await getattr(scoped_fs, operation)(_user(), ("acme", "users", "u-1", "note.md"), *args)

    assert storage.calls == []


@pytest.mark.parametrize("segments", [("acme", "users"), ("acme", "users", "u-1")])
@pytest.mark.asyncio
async def test_retired_personal_directories_are_not_listed_or_statable(segments):
    scoped_fs, storage, _rebac = _scoped_filesystem()
    for operation in (scoped_fs.list_area, scoped_fs.stat_area):
        with pytest.raises(FileNotFoundError, match="Unsupported team sub-area"):
            await operation(_user(), segments)
    assert storage.calls == []


@pytest.mark.asyncio
async def test_retired_personal_area_is_not_searchable():
    scoped_fs, storage, _rebac = _scoped_filesystem()
    with pytest.raises(FileNotFoundError, match="Unsupported team sub-area"):
        await scoped_fs.grep_area(_user(), "note", ("acme", "users"))
    await scoped_fs.grep_area(_user(), "note", ("acme",))
    assert all("users/u-1" not in args for _name, args, _kwargs in storage.calls)


# ── agent-per-user (agents) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_user_path_routes_to_storage():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    await scoped_fs.write_bytes_area(_user(), ("acme", "agents", "slide-builder", "users", "u-1", "draft.pptx"), b"x")

    assert storage.calls == [
        (
            "put",
            (_user(), "agents/slide-builder/users/u-1/draft.pptx", b"x"),
            {"owner_override": "acme", "root_prefix": "teams"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_user_path_requires_users_segment():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    with pytest.raises(FileNotFoundError, match="Agent path must be"):
        await scoped_fs.cat_area(_user(), ("acme", "agents", "slide-builder", "draft.pptx"))


# ── agent-config assets (agents/{id}/config, #1903) ─────────────────────────


@pytest.mark.asyncio
async def test_agent_config_read_checks_membership_only():
    scoped_fs, storage, rebac = _scoped_filesystem()

    # Any member chatting with the agent fetches config assets: read is gated by
    # CAN_ACCESS_FILES (box entry) only, not the stronger CAN_UPDATE_RESOURCES.
    content = await scoped_fs.cat_area(_user(), ("acme", "agents", "slide-builder", "config", "template.pptx"))

    assert content == "hello"
    assert rebac.checks == [(_user(), TeamPermission.CAN_ACCESS_FILES, "acme")]
    assert storage.calls == [
        (
            "get_text",
            (_user(), "agents/slide-builder/config/template.pptx"),
            {"owner_override": "acme", "root_prefix": "teams"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_config_read_bytes_routes_to_storage():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    data = await scoped_fs.read_bytes_area(_user(), ("acme", "agents", "slide-builder", "config", "template.pptx"))

    assert data == b"\x89PNG"
    assert storage.calls == [
        (
            "get_bytes",
            (_user(), "agents/slide-builder/config/template.pptx"),
            {"owner_override": "acme", "root_prefix": "teams"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_config_write_requires_update_resources():
    scoped_fs, storage, rebac = _scoped_filesystem()

    await scoped_fs.write_bytes_area(_user(), ("acme", "agents", "slide-builder", "config", "template.pptx"), b"x")

    # Membership first (box entry), then the stronger write permission — same
    # Agent-config assets are a team-owned, admin-managed area.
    assert rebac.checks == [
        (_user(), TeamPermission.CAN_ACCESS_FILES, "acme"),
        (_user(), TeamPermission.CAN_UPDATE_RESOURCES, "acme"),
    ]
    assert storage.calls == [
        (
            "put",
            (_user(), "agents/slide-builder/config/template.pptx", b"x"),
            {"owner_override": "acme", "root_prefix": "teams"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_config_write_denied_without_update_resources():
    scoped_fs, storage, _rebac = _scoped_filesystem()
    scoped_fs.rebac = _DenyUpdateRebac()

    with pytest.raises(PermissionError, match="update denied"):
        await scoped_fs.write_bytes_area(_user(), ("acme", "agents", "slide-builder", "config", "template.pptx"), b"x")

    # The write permission is enforced before any storage mutation.
    assert storage.calls == []


@pytest.mark.asyncio
async def test_agent_config_delete_requires_update_resources():
    scoped_fs, storage, rebac = _scoped_filesystem()

    await scoped_fs.delete_area(_user(), ("acme", "agents", "slide-builder", "config", "old.pptx"))

    assert rebac.checks == [
        (_user(), TeamPermission.CAN_ACCESS_FILES, "acme"),
        (_user(), TeamPermission.CAN_UPDATE_RESOURCES, "acme"),
    ]
    assert storage.calls == [
        (
            "delete",
            (_user(), "agents/slide-builder/config/old.pptx"),
            {"owner_override": "acme", "root_prefix": "teams"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_id_root_lists_users_and_config():
    scoped_fs, _storage, rebac = _scoped_filesystem()

    entries = await scoped_fs.list_area(_user(), ("acme", "agents", "slide-builder"))

    # An agent box exposes exactly its two sub-areas: per-user space and the
    # shared agent-config area (#1903).
    assert [entry.path for entry in entries] == ["users", "config"]
    assert rebac.checks == [(_user(), TeamPermission.CAN_ACCESS_FILES, "acme")]


@pytest.mark.asyncio
async def test_agent_config_stat_is_synthetic_dir():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    entry = await scoped_fs.stat_area(_user(), ("acme", "agents", "slide-builder", "config"))

    # The `config` directory level is synthetic (not a stored object) — no
    # storage round-trip, and it reports as a directory.
    assert entry.path == "config"
    assert entry.is_dir()
    assert storage.calls == []


@pytest.mark.asyncio
async def test_agent_config_grep_scope_routes_to_storage():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    matches = await scoped_fs.grep_area(_user(), "logo", ("acme", "agents", "slide-builder", "config"))

    assert matches == ["/teams/acme/notes.txt"]
    assert storage.calls[-1] == (
        "grep",
        (_user(), "logo", "agents/slide-builder/config"),
        {"owner_override": "acme", "root_prefix": "teams"},
    )


@pytest.mark.asyncio
async def test_agent_path_neither_users_nor_config_is_rejected():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    # A path under agents/{id} that is neither users/ nor config/ is malformed
    # and must be rejected before any storage access.
    with pytest.raises(FileNotFoundError, match="Agent path must be"):
        await scoped_fs.cat_area(_user(), ("acme", "agents", "slide-builder", "bogus", "x.pptx"))

    assert storage.calls == []


@pytest.mark.asyncio
async def test_agent_users_other_uid_still_rejected():
    scoped_fs, storage, _rebac = _scoped_filesystem()

    # Regression: the config sub-area must not have loosened the ownership rule
    # on the sibling per-user agent space.
    with pytest.raises(PermissionError, match="another user's personal space"):
        await scoped_fs.cat_area(_user(), ("acme", "agents", "slide-builder", "users", "someone-else", "draft.pptx"))

    assert storage.calls == []


# ── grep, roots, malformed ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_teams_root_lists_only_readable_team_ids():
    scoped_fs, _storage, rebac = _scoped_filesystem()
    rebac.team_ids = ["team-2", "team-1"]

    entries = await scoped_fs.list_area(_user(), ())

    assert [entry.path for entry in entries] == ["team-1", "team-2"]
    assert rebac.lookup_calls == [(_user(), TeamPermission.CAN_ACCESS_FILES)]


@pytest.mark.asyncio
async def test_team_box_lists_subareas():
    scoped_fs, _storage, rebac = _scoped_filesystem()

    entries = await scoped_fs.list_area(_user(), ("acme",))

    assert [entry.path for entry in entries] == ["agents"]
    assert rebac.checks == [(_user(), TeamPermission.CAN_ACCESS_FILES, "acme")]


@pytest.mark.asyncio
async def test_rejects_unsupported_sub_area():
    scoped_fs, _storage, _rebac = _scoped_filesystem()

    with pytest.raises(FileNotFoundError, match="Unsupported team sub-area"):
        await scoped_fs.cat_area(_user(), ("acme", "bogus", b"x"))


# ── membership-only filesystem access ──────────────────────────────────────


@pytest.mark.asyncio
async def test_teams_root_hides_teams_visible_only_through_public():
    scoped_fs, _storage, _rebac = _scoped_filesystem()
    rebac = _PublicOnlyRebac()
    rebac.team_ids = ["someone-elses-team"]
    scoped_fs.rebac = rebac

    entries = await scoped_fs.list_area(_user(), ())

    # Marketplace visibility is not filesystem access: the team is discoverable
    # but its box must not show up in /teams.
    assert entries == []
    assert rebac.lookup_calls == [(_user(), TeamPermission.CAN_ACCESS_FILES)]


@pytest.mark.asyncio
async def test_public_only_team_grep_is_denied():
    scoped_fs, storage, _rebac = _scoped_filesystem()
    scoped_fs.rebac = _PublicOnlyRebac()

    with pytest.raises(PermissionError, match="can_access_files denied"):
        await scoped_fs.grep_area(_user(), "secret", ("someone-elses-team",))

    assert storage.calls == []


@pytest.mark.asyncio
async def test_member_team_stays_reachable():
    scoped_fs, storage, rebac = _scoped_filesystem()
    rebac.team_ids = ["acme"]

    entries = await scoped_fs.list_area(_user(), ())
    content = await scoped_fs.cat_area(_user(), ("acme", "agents", "slide-builder", "users", "u-1", "notes.md"))

    assert [entry.path for entry in entries] == ["acme"]
    assert content == "hello"
    assert storage.calls == [
        ("get_text", (_user(), "agents/slide-builder/users/u-1/notes.md"), {"owner_override": "acme", "root_prefix": "teams"}),
    ]
