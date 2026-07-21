import logging

import pytest
from fred_core import (
    AuthorizationError,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
    KeycloakUser,
)
from fred_core.security.models import Resource

from knowledge_flow_backend.features.filesystem.mcp_fs_service import (
    FilesystemReadBounds,
    McpFilesystemService,
)
from knowledge_flow_backend.features.filesystem.virtual_fs_contract import FileReadPage


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated MCP filesystem service tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
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
    """Stub of the team-rooted scoped-area router: methods take (user, segments)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list_area(self, *args, **kwargs):
        self.calls.append(("list_area", args, kwargs))
        return [_file("notes.txt")]

    async def stat_area(self, *args, **kwargs):
        self.calls.append(("stat_area", args, kwargs))
        return _file("notes.txt")

    async def cat_area(self, *args, **kwargs):
        self.calls.append(("cat_area", args, kwargs))
        return "hello"

    async def read_bytes_area(self, *args, **kwargs):
        self.calls.append(("read_bytes_area", args, kwargs))
        return b"\x89PNG"

    async def write_bytes_area(self, *args, **kwargs):
        self.calls.append(("write_bytes_area", args, kwargs))

    async def write_area(self, *args, **kwargs):
        self.calls.append(("write_area", args, kwargs))

    async def delete_area(self, *args, **kwargs):
        self.calls.append(("delete_area", args, kwargs))

    async def grep_area(self, *args, **kwargs):
        self.calls.append(("grep_area", args, kwargs))
        return ["/teams/acme/shared/notes.txt"]

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
    """Build one MCP filesystem service with explicit collaborator stubs."""

    service = object.__new__(McpFilesystemService)
    scoped_areas = _ScopedAreaStub()
    corpus_area = _CorpusAreaStub()
    service.scoped_areas = scoped_areas
    service.corpus_area = corpus_area
    service.read_bounds = FilesystemReadBounds(
        default_limit=100,
        max_limit=500,
        default_max_chars=20_000,
        absolute_max_chars=50_000,
    )
    return service, scoped_areas, corpus_area


@pytest.mark.asyncio
async def test_list_root_returns_teams_and_corpus(app_context):
    service, _scoped_areas, _corpus_area = _service()

    entries = await service.list(_user(), "")

    # Top level of the unified layout: /teams (always) + /corpus (when it has content).
    assert [entry.path for entry in entries] == ["teams", "corpus"]


@pytest.mark.asyncio
async def test_list_routes_teams_path_to_scoped_area(app_context):
    service, scoped_areas, _corpus_area = _service()

    await service.list(_user(), "/teams/acme/shared/reports")

    call_name, args, kwargs = scoped_areas.calls[-1]
    assert call_name == "list_area"
    assert args == (_user(), ("acme", "shared", "reports"))
    assert kwargs == {}


@pytest.mark.asyncio
async def test_list_reraises_authorization_error_without_error_log(app_context, caplog):
    """`AuthorizationError` is an expected, routine denial (ReBAC already logs
    one bounded WARNING at the point of denial) — `list()` must propagate it
    unchanged for the controller's `AuthorizationError -> 403` mapping, without
    also emitting its own ERROR-level traceback (previously it did, via a bare
    `except Exception: logger.exception(...)`, producing a duplicate stack
    trace for a non-bug outcome)."""
    service, scoped_areas, _corpus_area = _service()

    async def raise_authorization_error(*args, **kwargs):
        raise AuthorizationError("u-1", "can_read", Resource.TEAM, "Not authorized")

    scoped_areas.list_area = raise_authorization_error

    with caplog.at_level(logging.ERROR):
        with pytest.raises(AuthorizationError):
            await service.list(_user(), "/teams/personal-u-1")

    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


@pytest.mark.asyncio
async def test_list_rejects_unknown_top_level_area(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(ValueError, match="Unknown filesystem area"):
        await service.list(_user(), "/workspace/old")


@pytest.mark.asyncio
async def test_list_routes_corpus_paths_to_corpus_area(app_context):
    service, _scoped_areas, corpus_area = _service()

    entries = await service.list(_user(), "/corpus/CIR")

    assert [entry.path for entry in entries] == ["CIR"]
    assert corpus_area.calls[-1] == ("list_area", (_user(), ("CIR",)), {})


@pytest.mark.asyncio
async def test_list_stamps_agent_provenance(app_context):
    # FILES-04 G4: a file listed under the agents subtree comes back tagged
    # agent_generated, derived from its full virtual path.
    service, _scoped_areas, _corpus_area = _service()

    entries = await service.list(_user(), "/teams/acme/agents/inst-7/users/u-1/outputs")

    entry = entries[0]
    assert entry.path == "notes.txt"
    assert entry.origin == "agent_generated"
    assert entry.producer == "agent:inst-7"
    assert entry.created_by == "u-1"


@pytest.mark.asyncio
async def test_list_stamps_mon_espace_provenance(app_context):
    service, _scoped_areas, _corpus_area = _service()

    entries = await service.list(_user(), "/teams/acme/users/u-1")

    assert entries[0].origin == "uploaded"
    assert entries[0].producer == "human"
    assert entries[0].created_by == "u-1"


@pytest.mark.asyncio
async def test_stat_stamps_provenance_from_requested_path(app_context):
    service, _scoped_areas, _corpus_area = _service()

    entry = await service.stat(_user(), "/teams/acme/agents/inst-7/users/u-1/outputs/notes.txt")

    assert entry.origin == "agent_generated"
    assert entry.producer == "agent:inst-7"


@pytest.mark.asyncio
async def test_list_root_entries_carry_no_provenance(app_context):
    service, _scoped_areas, _corpus_area = _service()

    entries = await service.list(_user(), "")

    assert all(entry.origin is None for entry in entries)


@pytest.mark.asyncio
async def test_read_file_formats_numbered_excerpt(app_context):
    service, _scoped_areas, corpus_area = _service()

    excerpt = await service.read_file(_user(), "/corpus/CIR/report.md", offset=1, limit=2)

    assert excerpt == "2 | line2\n3 | line3"
    assert corpus_area.calls[-1] == ("cat_area", (_user(), ("CIR", "report.md")), {})


@pytest.mark.asyncio
async def test_read_file_page_returns_structured_page(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _cat(user, path):
        del user, path
        return "alpha\nbeta\ngamma"

    service.cat = _cat

    page = await service.read_file_page(_user(), "/teams/acme/shared/report.md", offset=0, limit=3, max_chars=12)

    assert page == FileReadPage(
        path="/teams/acme/shared/report.md",
        content="1 | alpha",
        start_line=0,
        end_line=0,
        returned_lines=1,
        total_lines=3,
        has_more=True,
        next_offset=1,
        truncated=True,
    )


@pytest.mark.asyncio
async def test_read_file_page_reads_corpus_document_uid_path(app_context):
    service, _scoped_areas, corpus_area = _service()

    page = await service.read_file_page(
        _user(),
        "/corpus/documents/doc-1/preview.md",
        offset=0,
        limit=2,
        max_chars=100,
    )

    assert page.content == "1 | line1\n2 | line2"
    assert page.next_offset == 2
    assert corpus_area.calls[-1] == ("cat_area", (_user(), ("documents", "doc-1", "preview.md")), {})


@pytest.mark.asyncio
async def test_read_file_applies_default_bounds_when_caller_omits_them(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _cat(user, path):
        del user, path
        return "\n".join(f"line {index}" for index in range(1, 200))

    service.cat = _cat
    service.read_bounds = FilesystemReadBounds(
        default_limit=2,
        max_limit=500,
        default_max_chars=100,
        absolute_max_chars=50_000,
    )

    excerpt = await service.read_file(_user(), "/teams/acme/shared/report.md")

    assert excerpt == "1 | line 1\n2 | line 2"


@pytest.mark.asyncio
async def test_read_file_rejects_limit_above_configured_max(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(ValueError, match="limit must be <= 500"):
        await service.read_file(_user(), "/teams/acme/shared/report.md", limit=501)


@pytest.mark.asyncio
async def test_read_file_rejects_max_chars_above_configured_max(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(ValueError, match="max_chars must be <= 50000"):
        await service.read_file(_user(), "/teams/acme/shared/report.md", max_chars=50_001)


@pytest.mark.asyncio
async def test_read_file_truncates_rendered_excerpt_to_max_chars(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _cat(user, path):
        del user, path
        return "alpha\nbeta\ngamma"

    service.cat = _cat

    excerpt = await service.read_file(_user(), "/teams/acme/shared/report.md", limit=3, max_chars=10)

    assert excerpt == "1 | alpha"


@pytest.mark.asyncio
async def test_read_file_remains_plain_text_compatible_when_page_metadata_exists(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _cat(user, path):
        del user, path
        return "a\nb\nc"

    service.cat = _cat

    excerpt = await service.read_file(_user(), "/teams/acme/shared/report.md", offset=1, limit=2, max_chars=100)

    assert isinstance(excerpt, str)
    assert excerpt == "2 | b\n3 | c"


@pytest.mark.asyncio
async def test_copy_to_shared_places_file_and_tags_share_copy(app_context):
    # G5: copy a private file into Espace d'equipe; it lands under shared/files and
    # reads back as a share-copy (partagé).
    service, scoped_areas, _corpus_area = _service()

    entry = await service.copy_to_shared(_user(), "/teams/acme/users/u-1/outputs/q3.pptx")

    writes = [c for c in scoped_areas.calls if c[0] == "write_bytes_area"]
    assert writes[-1][1][1] == ("acme", "shared", "files", "q3.pptx")
    assert entry.origin == "shared_copy"


@pytest.mark.asyncio
async def test_copy_to_shared_suffixes_on_name_collision(app_context):
    # The stub's shared/files already contains "notes.txt", so a copy of the same
    # name is placed as "notes (2).txt" (no-clobber).
    service, scoped_areas, _corpus_area = _service()

    await service.copy_to_shared(_user(), "/teams/acme/users/u-1/notes.txt")

    writes = [c for c in scoped_areas.calls if c[0] == "write_bytes_area"]
    assert writes[-1][1][1] == ("acme", "shared", "files", "notes (2).txt")


@pytest.mark.asyncio
async def test_copy_to_shared_rejects_corpus_source(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(PermissionError):
        await service.copy_to_shared(_user(), "/corpus/CIR/report.md")


def test_unique_name_suffixing():
    from knowledge_flow_backend.features.filesystem.mcp_fs_service import _unique_name

    assert _unique_name("a.txt", set()) == "a.txt"
    assert _unique_name("a.txt", {"a.txt"}) == "a (2).txt"
    assert _unique_name("a.txt", {"a.txt", "a (2).txt"}) == "a (3).txt"
    assert _unique_name("noext", {"noext"}) == "noext (2)"


@pytest.mark.asyncio
async def test_write_rejects_corpus_area(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(PermissionError, match="Corpus area is read-only"):
        await service.write(_user(), "/corpus/CIR/report.md", "hello")


@pytest.mark.asyncio
async def test_read_bytes_routes_teams_path_to_scoped_area(app_context):
    service, scoped_areas, _corpus_area = _service()

    data = await service.read_bytes(_user(), "/teams/acme/shared/templates/deck.pptx")

    assert data == b"\x89PNG"
    assert scoped_areas.calls[-1] == ("read_bytes_area", (_user(), ("acme", "shared", "templates", "deck.pptx")), {})


@pytest.mark.asyncio
async def test_read_bytes_rejects_corpus_area(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(PermissionError, match="Corpus binaries are served by the content API"):
        await service.read_bytes(_user(), "/corpus/CIR/original.pptx")


@pytest.mark.asyncio
async def test_write_bytes_routes_teams_path_to_scoped_area(app_context):
    service, scoped_areas, _corpus_area = _service()

    await service.write_bytes(_user(), "/teams/acme/users/u-1/outputs/q3.pptx", b"\x00\x01")

    assert scoped_areas.calls[-1] == (
        "write_bytes_area",
        (_user(), ("acme", "users", "u-1", "outputs", "q3.pptx"), b"\x00\x01"),
        {},
    )


@pytest.mark.asyncio
async def test_write_bytes_rejects_corpus_area(app_context):
    service, _scoped_areas, _corpus_area = _service()

    with pytest.raises(PermissionError, match="Corpus area is read-only"):
        await service.write_bytes(_user(), "/corpus/CIR/x.pptx", b"\x00")


@pytest.mark.asyncio
async def test_grep_root_combines_team_and_corpus_results(app_context):
    service, scoped_areas, corpus_area = _service()

    matches = await service.grep(_user(), "report", "")

    assert matches == ["/teams/acme/shared/notes.txt", "/corpus/CIR/report.md"]
    # Root grep fans out once into the team area (which itself only reaches readable scopes).
    assert scoped_areas.calls == [("grep_area", (_user(), "report", ()), {})]
    assert corpus_area.calls[-1] == ("grep_area", (_user(), "report", ()), {})


@pytest.mark.asyncio
async def test_glob_matches_against_visible_absolute_paths(app_context):
    service, _scoped_areas, _corpus_area = _service()

    async def _walk_visible_tree(user, path="/"):
        del user, path
        return [
            _file("/teams/acme/shared/report.md"),
            _file("/teams/acme/shared/archive/q1.md"),
            _dir("/teams/acme/shared/archive"),
        ]

    service._walk_visible_tree = _walk_visible_tree

    matches = await service.glob(_user(), "**/*.md", path="/teams/acme/shared")

    assert matches == ["/teams/acme/shared/report.md", "/teams/acme/shared/archive/q1.md"]


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
        "/teams/acme/shared/note.md",
        old_string="draft",
        new_string="final",
    )

    assert result == {"path": "/teams/acme/shared/note.md", "occurrences": 1}
    assert captured[0][1:] == ("/teams/acme/shared/note.md", "final content")
