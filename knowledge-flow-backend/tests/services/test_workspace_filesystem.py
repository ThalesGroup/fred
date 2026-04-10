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
        groups=["admins"],
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
    def __init__(self) -> None:
        self.existing_paths: set[str] = set()
        self.mkdir_calls: list[str] = []
        self.write_calls: list[tuple[str, bytes | str]] = []
        self.list_results: list[FilesystemResourceInfoResult] = []
        self.grep_results: list[str] = []

    async def exists(self, path: str) -> bool:
        return path in self.existing_paths

    async def mkdir(self, path: str) -> None:
        self.mkdir_calls.append(path)
        self.existing_paths.add(path)

    async def write(self, path: str, data: bytes | str) -> None:
        self.write_calls.append((path, data))

    async def read(self, path: str) -> bytes:
        return f"bytes:{path}".encode()

    async def cat(self, path: str) -> str:
        return f"text:{path}"

    async def delete(self, path: str) -> None:
        self.deleted_path = path

    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        return _file(path, size=42)

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
