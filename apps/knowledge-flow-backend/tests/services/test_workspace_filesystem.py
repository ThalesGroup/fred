from __future__ import annotations

import pytest
from fred_core import KeycloakUser
from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)

from knowledge_flow_backend.features.filesystem.workspace_filesystem import (
    WorkspaceFilesystem,
)


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated workspace filesystem tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
    )


def _file(path: str, size: int = 1) -> FilesystemResourceInfoResult:
    """Build one file entry returned by the fake lower filesystem."""

    return FilesystemResourceInfoResult(
        path=path,
        size=size,
        type=FilesystemResourceInfo.FILE,
        modified=None,
    )


class _FakeFilesystem:
    """Mirrors the real backends' key ambiguity: `exists()` is true for a file OR a
    directory (empty or not) alike — only `stat()` (via `directory_paths`, or a
    prefix match against `list_results`) tells them apart, same as MinIO/GCS's own
    prefix-listing fallback and local's `Path.is_file()`/`is_dir()`."""

    def __init__(self) -> None:
        self.existing_paths: set[str] = set()
        self.directory_paths: set[str] = set()
        self.mkdir_calls: list[str] = []
        self.write_calls: list[tuple[str, bytes | str]] = []
        self.list_results: list[FilesystemResourceInfoResult] = []
        self.grep_results: list[str] = []

    def _has_descendants(self, path: str) -> bool:
        prefix = path.rstrip("/") + "/"
        return any(entry.path.startswith(prefix) for entry in self.list_results)

    async def exists(self, path: str) -> bool:
        return path in self.existing_paths or path in self.directory_paths or self._has_descendants(path)

    async def mkdir(self, path: str) -> None:
        self.mkdir_calls.append(path)
        self.directory_paths.add(path)

    async def write(self, path: str, data: bytes | str) -> None:
        self.write_calls.append((path, data))

    async def read(self, path: str) -> bytes:
        return f"bytes:{path}".encode()

    async def cat(self, path: str) -> str:
        return f"text:{path}"

    async def delete(self, path: str) -> None:
        self.deleted_path = path

    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        if path in self.existing_paths:
            return _file(path, size=42)
        if path in self.directory_paths or self._has_descendants(path):
            return FilesystemResourceInfoResult(path=path, size=None, type=FilesystemResourceInfo.DIRECTORY, modified=None)
        raise FileNotFoundError(path)

    async def list(self, prefix: str) -> list[FilesystemResourceInfoResult]:
        self.list_prefix = prefix
        return list(self.list_results)

    async def grep(self, pattern: str, prefix: str) -> list[str]:
        self.grep_call = (pattern, prefix)
        return list(self.grep_results)


@pytest.mark.asyncio
async def test_list_returns_only_direct_children():
    fs = _FakeFilesystem()
    fs.list_results = [
        _file("users/u-1/reports/2026/summary.md"),
        _file("users/u-1/reports/2025/summary.md"),
        _file("users/u-1/notes.txt"),
    ]
    workspace = WorkspaceFilesystem(fs)

    entries = await workspace.list(_user())

    assert [entry.path for entry in entries] == ["notes.txt", "reports"]
    assert entries[0].is_file()
    assert entries[1].is_dir()


@pytest.mark.asyncio
async def test_list_respects_owner_override_and_root_prefix():
    fs = _FakeFilesystem()
    workspace = WorkspaceFilesystem(fs)

    await workspace.list(
        _user(),
        "config",
        owner_override="agent-1/config",
        root_prefix="agents",
    )

    assert fs.list_prefix == "agents/agent-1/config/config"


@pytest.mark.asyncio
async def test_put_creates_parent_prefix_when_missing():
    fs = _FakeFilesystem()
    workspace = WorkspaceFilesystem(fs)

    path = await workspace.put(_user(), "reports/summary.txt", "hello")

    assert path == "users/u-1/reports/summary.txt"
    assert fs.mkdir_calls == ["users/u-1/reports"]
    assert fs.write_calls == [("users/u-1/reports/summary.txt", "hello")]


@pytest.mark.asyncio
async def test_grep_returns_namespace_relative_paths():
    fs = _FakeFilesystem()
    fs.grep_results = [
        "users/u-1/reports/summary.md",
        "users/u-1/reports/archive/q1.md",
    ]
    workspace = WorkspaceFilesystem(fs)

    matches = await workspace.grep(_user(), "summary", "reports")

    assert fs.grep_call == ("summary", "users/u-1/reports")
    assert matches == ["reports/summary.md", "reports/archive/q1.md"]


@pytest.mark.asyncio
async def test_rename_moves_a_single_file():
    fs = _FakeFilesystem()
    fs.existing_paths.add("users/u-1/notes.txt")
    workspace = WorkspaceFilesystem(fs)

    await workspace.rename(_user(), "notes.txt", "meeting-notes.txt")

    assert fs.write_calls == [("users/u-1/meeting-notes.txt", b"bytes:users/u-1/notes.txt")]
    assert fs.deleted_path == "users/u-1/notes.txt"


@pytest.mark.asyncio
async def test_rename_rejects_when_destination_already_exists():
    fs = _FakeFilesystem()
    fs.existing_paths.add("users/u-1/notes.txt")
    fs.existing_paths.add("users/u-1/final.txt")
    workspace = WorkspaceFilesystem(fs)

    with pytest.raises(ValueError, match="already exists"):
        await workspace.rename(_user(), "notes.txt", "final.txt")


@pytest.mark.asyncio
async def test_rename_moves_every_descendant_of_a_folder():
    fs = _FakeFilesystem()
    fs.list_results = [
        _file("users/u-1/reports/summary.md"),
        _file("users/u-1/reports/archive/q1.md"),
    ]
    workspace = WorkspaceFilesystem(fs)

    await workspace.rename(_user(), "reports", "reports-2026")

    assert set(fs.write_calls) == {
        ("users/u-1/reports-2026/summary.md", b"bytes:users/u-1/reports/summary.md"),
        ("users/u-1/reports-2026/archive/q1.md", b"bytes:users/u-1/reports/archive/q1.md"),
    }


@pytest.mark.asyncio
async def test_rename_raises_when_source_does_not_exist():
    fs = _FakeFilesystem()
    workspace = WorkspaceFilesystem(fs)

    with pytest.raises(FileNotFoundError):
        await workspace.rename(_user(), "missing", "renamed")


@pytest.mark.asyncio
async def test_rename_preserves_an_empty_folder():
    fs = _FakeFilesystem()
    fs.directory_paths.add("users/u-1/empty")
    workspace = WorkspaceFilesystem(fs)

    await workspace.rename(_user(), "empty", "renamed-empty")

    assert fs.mkdir_calls == ["users/u-1/renamed-empty"]
    assert fs.deleted_path == "users/u-1/empty"


@pytest.mark.asyncio
async def test_list_recursive_files_skips_directories_outside_prefix():
    fs = _FakeFilesystem()
    fs.list_results = [
        _file("users/u-1/reports/summary.md"),
        _file("users/u-1/reports/archive/q1.md"),
    ]
    workspace = WorkspaceFilesystem(fs)

    entries = await workspace.list_recursive_files(_user(), "reports")

    assert {e.path for e in entries} == {
        "users/u-1/reports/summary.md",
        "users/u-1/reports/archive/q1.md",
    }
