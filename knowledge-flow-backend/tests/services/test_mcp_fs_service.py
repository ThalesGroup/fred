import pytest
from fred_core import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
    KeycloakUser,
)

from knowledge_flow_backend.features.filesystem.mcp_fs_service import (
    McpFilesystemService,
)
from knowledge_flow_backend.features.filesystem.virtual_fs_contract import VirtualArea


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated MCP filesystem service tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
        groups=["admins"],
    )


def _dir(path: str) -> FilesystemResourceInfoResult:
    """Build one directory entry for service-level tests."""

    return FilesystemResourceInfoResult(
        path=path,
        size=None,
        type=FilesystemResourceInfo.DIRECTORY,
        modified=None,
    )


def _file(path: str) -> FilesystemResourceInfoResult:
    """Build one file entry for service-level tests."""

    return FilesystemResourceInfoResult(
        path=path,
        size=1,
        type=FilesystemResourceInfo.FILE,
        modified=None,
    )


class _ScopedAreaStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.agent_root_entries: list[FilesystemResourceInfoResult] = []
        self.team_root_entries: list[FilesystemResourceInfoResult] = []

    async def list_area(self, *args, **kwargs):
        self.calls.append(("list_area", args, kwargs))
        area = args[1]
        segments = args[2]
        if area == VirtualArea.AGENT and segments == ():
            return self.agent_root_entries
        if area == VirtualArea.TEAM and segments == ():
            return self.team_root_entries
        return [_file("notes.txt")]

    async def stat_area(self, *args, **kwargs):
        self.calls.append(("stat_area", args, kwargs))
        return _file("notes.txt")

    async def cat_area(self, *args, **kwargs):
        self.calls.append(("cat_area", args, kwargs))
        return "hello"

    async def write_area(self, *args, **kwargs):
        self.calls.append(("write_area", args, kwargs))

    async def delete_area(self, *args, **kwargs):
        self.calls.append(("delete_area", args, kwargs))

    async def grep_area(self, *args, **kwargs):
        self.calls.append(("grep_area", args, kwargs))
        area = args[1]
        segments = args[3]
        if area in {VirtualArea.AGENT, VirtualArea.TEAM} and segments == ():
            return []
        return ["/workspace/notes.txt"]

    async def mkdir_area(self, *args, **kwargs):
        self.calls.append(("mkdir_area", args, kwargs))


class _CorpusAreaStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list_area(self, *args, **kwargs):
        self.calls.append(("list_area", args, kwargs))
        return [_dir("CIR")]

    async def stat_area(self, *args, **kwargs):
        self.calls.append(("stat_area", args, kwargs))
        return _dir("CIR")

    async def cat_area(self, *args, **kwargs):
        self.calls.append(("cat_area", args, kwargs))
        return "line1\nline2\nline3"

    async def grep_area(self, *args, **kwargs):
        self.calls.append(("grep_area", args, kwargs))
        return ["corpus/CIR/report.md"]


def _service() -> tuple[McpFilesystemService, _ScopedAreaStub, _CorpusAreaStub]:
    """
    Build one MCP filesystem service with explicit collaborator stubs.

    Why this exists:
    - service tests should verify routing at the public interface, not real backend wiring
    - stubbing collaborators keeps failures focused on path dispatch and response shaping

    How to use:
    - call once per test and inspect the returned stubs after invoking a public method

    Example:
    - `service, scoped_areas, corpus_area = _service()`
    """

    service = object.__new__(McpFilesystemService)
    scoped_areas = _ScopedAreaStub()
    corpus_area = _CorpusAreaStub()
    service.scoped_areas = scoped_areas
    service.corpus_area = corpus_area
    return service, scoped_areas, corpus_area


@pytest.mark.asyncio
async def test_list_root_returns_visible_top_level_directories(app_context):
    service, _scoped_areas, _corpus_area = _service()

    entries = await service.list(_user(), "")

    assert [entry.path for entry in entries] == ["workspace", "corpus"]


@pytest.mark.asyncio
async def test_list_root_includes_agent_and_team_only_when_readable(app_context):
    service, scoped_areas, _corpus_area = _service()
    scoped_areas.agent_root_entries = [_dir("agent-1")]
    scoped_areas.team_root_entries = [_dir("team-1")]

    entries = await service.list(_user(), "")

    assert [entry.path for entry in entries] == ["workspace", "agent", "team", "corpus"]


@pytest.mark.asyncio
async def test_list_routes_user_alias_to_workspace_area(app_context):
    service, scoped_areas, _corpus_area = _service()

    await service.list(_user(), "/user/reports")

    call_name, args, kwargs = scoped_areas.calls[-1]
    assert call_name == "list_area"
    assert args[1] == VirtualArea.WORKSPACE
    assert args[2] == ("reports",)
    assert kwargs == {}


@pytest.mark.asyncio
async def test_list_routes_corpus_paths_to_corpus_area(app_context):
    service, _scoped_areas, corpus_area = _service()

    entries = await service.list(_user(), "/corpus/CIR")

    assert [entry.path for entry in entries] == ["CIR"]
    assert corpus_area.calls[-1] == ("list_area", (_user(), ("CIR",)), {})


@pytest.mark.asyncio
async def test_read_file_formats_numbered_excerpt(app_context):
    service, _scoped_areas, corpus_area = _service()

    excerpt = await service.read_file(_user(), "/corpus/CIR/report.md", offset=1, limit=2)

    assert excerpt == "2 | line2\n3 | line3"
    assert corpus_area.calls[-1] == ("cat_area", (_user(), ("CIR", "report.md")), {})


@pytest.mark.asyncio
async def test_write_rejects_corpus_area(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(PermissionError, match="Corpus area is read-only"):
        await service.write(_user(), "/corpus/CIR/report.md", "hello")


@pytest.mark.asyncio
async def test_grep_root_combines_workspace_and_corpus_results(app_context):
    service, scoped_areas, corpus_area = _service()

    matches = await service.grep(_user(), "report", "")

    assert matches == ["/workspace/notes.txt", "/corpus/CIR/report.md"]
    assert scoped_areas.calls[0] == (
        "grep_area",
        (_user(), VirtualArea.WORKSPACE, "report", ()),
        {},
    )
    assert scoped_areas.calls[1] == (
        "grep_area",
        (_user(), VirtualArea.AGENT, "report", ()),
        {},
    )
    assert scoped_areas.calls[2] == (
        "grep_area",
        (_user(), VirtualArea.TEAM, "report", ()),
        {},
    )
    assert corpus_area.calls[-1] == ("grep_area", (_user(), "report", ()), {})


@pytest.mark.asyncio
async def test_glob_matches_against_visible_absolute_paths(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _walk_visible_tree(user, path="/"):
        del user, path
        return [
            _file("/workspace/report.md"),
            _file("/workspace/archive/q1.md"),
            _dir("/workspace/archive"),
        ]

    service._walk_visible_tree = _walk_visible_tree

    matches = await service.glob(_user(), "**/*.md", path="/workspace")

    assert matches == ["/workspace/report.md", "/workspace/archive/q1.md"]


@pytest.mark.asyncio
async def test_edit_file_rewrites_content_and_returns_occurrence_count(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _cat(user, path):
        del user, path
        return "draft content"

    captured: list[tuple[KeycloakUser, str, str]] = []

    async def _write(user, path, data):
        captured.append((user, path, data))

    service.cat = _cat
    service.write = _write

    result = await service.edit_file(
        _user(),
        "/workspace/note.md",
        old_string="draft",
        new_string="final",
    )

    assert result == {"path": "/workspace/note.md", "occurrences": 1}
    assert captured[0][1:] == ("/workspace/note.md", "final content")
