# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for the team-rooted filesystem helpers on ToolContext (FILES-04)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.context import FsEntry, PublishedArtifact
from fred_sdk.contracts.runtime import WorkspaceFileNotFound


class _FakeWorkspaceFs:
    """In-memory WorkspaceFsPort stand-in recording author-relative paths."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.reads: list[str] = []

    def bind(self, binding) -> None:
        del binding

    async def read_bytes(self, path: str) -> bytes:
        self.reads.append(path)
        if path not in self.files:
            raise WorkspaceFileNotFound(path)
        return self.files[path]

    async def read_text(self, path: str) -> str:
        return (await self.read_bytes(path)).decode("utf-8")

    async def write(self, path, content, *, content_type=None, title=None) -> PublishedArtifact:
        self.files[path] = content
        return PublishedArtifact(
            key=path,
            file_name=path.split("/")[-1],
            size=len(content),
            href=f"/knowledge-flow/v1/fs/download/teams/acme/{path}",
            title=title,
        )

    async def ls(self, path: str = "") -> list[FsEntry]:
        return [FsEntry(path="deck.pptx", size=3)]

    async def delete(self, path: str) -> None:
        self.files.pop(path, None)


def _ctx(fs) -> ToolContext:
    ctx = object.__new__(ToolContext)
    ctx._runtime = SimpleNamespace(ports=SimpleNamespace(workspace_fs=fs))
    return ctx


def test_write_returns_artifact_and_round_trips():
    fs = _FakeWorkspaceFs()
    ctx = _ctx(fs)

    artifact = asyncio.run(ctx.write("outputs/q3.pptx", b"\x00\x01\x02"))

    assert isinstance(artifact, PublishedArtifact)
    assert artifact.file_name == "q3.pptx"
    assert artifact.size == 3
    # path encodes location now (no scope field); link rendering still works
    assert artifact.to_link_part().href.endswith("/fs/download/teams/acme/outputs/q3.pptx")
    assert asyncio.run(ctx.read_bytes("outputs/q3.pptx")) == b"\x00\x01\x02"


def test_write_encodes_str_content_as_utf8():
    fs = _FakeWorkspaceFs()
    ctx = _ctx(fs)

    asyncio.run(ctx.write("shared/outputs/note.md", "héllo"))

    assert asyncio.run(ctx.read("shared/outputs/note.md")) == "héllo"


def test_resolve_template_checks_user_then_team():
    fs = _FakeWorkspaceFs()
    fs.files["shared/templates/brand.pptx"] = b"TEAM"
    ctx = _ctx(fs)

    data = asyncio.run(ctx.resolve_template("brand.pptx"))

    assert data == b"TEAM"
    # user space first (miss), then the team's shared space (hit)
    assert fs.reads == ["templates/brand.pptx", "shared/templates/brand.pptx"]


def test_resolve_template_prefers_user_override():
    fs = _FakeWorkspaceFs()
    fs.files["templates/brand.pptx"] = b"MINE"
    fs.files["shared/templates/brand.pptx"] = b"TEAM"
    ctx = _ctx(fs)

    assert asyncio.run(ctx.resolve_template("brand.pptx")) == b"MINE"
    assert fs.reads == ["templates/brand.pptx"]


def test_resolve_template_raises_when_missing():
    ctx = _ctx(_FakeWorkspaceFs())

    with pytest.raises(WorkspaceFileNotFound):
        asyncio.run(ctx.resolve_template("absent.pptx"))


def test_ls_delegates_to_port():
    ctx = _ctx(_FakeWorkspaceFs())

    entries = asyncio.run(ctx.ls("shared/templates"))

    assert [e.path for e in entries] == ["deck.pptx"]


def test_missing_workspace_fs_port_raises():
    ctx = _ctx(None)

    with pytest.raises(RuntimeError, match="workspace_fs"):
        asyncio.run(ctx.read("outputs/x.txt"))
