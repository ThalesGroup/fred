# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for FredWorkspaceFs path relativization and operations (FILES-04)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_sdk.contracts.context import PublishedArtifact
from fred_sdk.contracts.runtime import WorkspaceFileNotFound

from fred_runtime.common.kf_workspace_client import (
    UserStorageBlob,
    UserStorageResourceInfo,
    UserStorageUploadResult,
    WorkspaceRetrievalError,
    WorkspaceShareLink,
)
from fred_runtime.integrations.v2_runtime.adapters import FredWorkspaceFs


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def fs_download_blob(self, path, token):
        self.calls.append(("download", path, token))
        if path.endswith("missing.bin"):
            raise WorkspaceRetrievalError("not found", status_code=404)
        return UserStorageBlob(b"DATA", "application/octet-stream", "x", 4)

    async def fs_upload(self, path, content, filename, content_type):
        self.calls.append(("upload", path, content, filename, content_type))
        return UserStorageUploadResult(
            key=path, file_name=filename, size=len(content), download_url=f"/dl/{path}"
        )

    async def fs_list(self, path, token):
        self.calls.append(("list", path, token))
        return [
            UserStorageResourceInfo(
                path="deck.pptx", size=3, type="file", modified=None
            )
        ]

    async def fs_delete(self, path, token):
        self.calls.append(("delete", path, token))

    async def fs_share(self, path, token):
        self.calls.append(("share", path, token))
        return WorkspaceShareLink(
            download_url=f"/dl/{path}?token=sig",
            file_name=path.rsplit("/", 1)[-1],
            size=4,
            mime="application/octet-stream",
        )


def _fs(client: _FakeClient | None = None) -> FredWorkspaceFs:
    fs = object.__new__(FredWorkspaceFs)
    fs._binding = SimpleNamespace(  # type: ignore[assignment]
        runtime_context=SimpleNamespace(
            team_id="acme",
            user_id="u-1",
            agent_instance_id="inst-7",
            access_token="tok",
        )
    )
    fs._settings = SimpleNamespace(team_id="acme")  # type: ignore[assignment]
    fs._workspace_client = client or _FakeClient()  # type: ignore[assignment]
    return fs


# ---- relativization (the §7.1 security rule) ----


def test_resolve_bare_path_goes_to_agent_space():
    # FILES-04 §3/§6: a bare agent write lands in the agent's own per-user space,
    # keyed by agent_instance_id — not Mon espace.
    assert (
        _fs()._resolve("outputs/q3.pptx")
        == "teams/acme/agents/inst-7/users/u-1/outputs/q3.pptx"
    )


def test_resolve_missing_agent_instance_raises():
    fs = _fs()
    fs._binding.runtime_context.agent_instance_id = None
    with pytest.raises(RuntimeError, match="agent instance"):
        fs._resolve("outputs/q3.pptx")


def test_resolve_shared_prefix_goes_to_team_space():
    assert (
        _fs()._resolve("shared/templates/brand.pptx")
        == "teams/acme/shared/templates/brand.pptx"
    )


def test_resolve_absolute_session_team_is_accepted():
    assert _fs()._resolve("/teams/acme/shared/x") == "teams/acme/shared/x"


def test_resolve_absolute_other_team_is_rejected():
    with pytest.raises(PermissionError, match="not the session team"):
        _fs()._resolve("/teams/edf/shared/x")


def test_resolve_rejects_parent_segments():
    with pytest.raises(ValueError, match="parent path segments"):
        _fs()._resolve("outputs/../../etc/secret")


def test_resolve_empty_requires_allow_root():
    fs = _fs()
    with pytest.raises(ValueError, match="empty"):
        fs._resolve("")
    assert fs._resolve("", allow_root=True) == "teams/acme/agents/inst-7/users/u-1"


# ---- operations ----


@pytest.mark.asyncio
async def test_read_bytes_maps_404_to_not_found():
    fs = _fs()
    with pytest.raises(WorkspaceFileNotFound):
        await fs.read_bytes("outputs/missing.bin")


@pytest.mark.asyncio
async def test_read_user_bytes_resolves_to_mon_espace():
    # G7: explicit read of the run user's Mon espace.
    client = _FakeClient()
    fs = _fs(client)
    await fs.read_user_bytes("templates/brand.pptx")
    assert client.calls[-1] == (
        "download",
        "teams/acme/users/u-1/templates/brand.pptx",
        "tok",
    )


@pytest.mark.asyncio
async def test_read_team_bytes_resolves_to_shared():
    # G7: explicit read of Espace d'equipe.
    client = _FakeClient()
    fs = _fs(client)
    await fs.read_team_bytes("templates/brand.pptx")
    assert client.calls[-1] == (
        "download",
        "teams/acme/shared/templates/brand.pptx",
        "tok",
    )


@pytest.mark.asyncio
async def test_read_bytes_resolves_and_returns_content():
    client = _FakeClient()
    fs = _fs(client)
    data = await fs.read_bytes("shared/templates/brand.pptx")
    assert data == b"DATA"
    assert client.calls[-1] == (
        "download",
        "teams/acme/shared/templates/brand.pptx",
        "tok",
    )


@pytest.mark.asyncio
async def test_write_uploads_to_agent_space_and_returns_artifact():
    client = _FakeClient()
    fs = _fs(client)
    artifact = await fs.write(
        "outputs/q3.pptx", b"\x00\x01", content_type="application/octet-stream"
    )
    assert isinstance(artifact, PublishedArtifact)
    assert artifact.file_name == "q3.pptx"
    assert artifact.href == "/dl/teams/acme/agents/inst-7/users/u-1/outputs/q3.pptx"
    assert client.calls[-1][0:2] == (
        "upload",
        "teams/acme/agents/inst-7/users/u-1/outputs/q3.pptx",
    )


@pytest.mark.asyncio
async def test_ls_lists_agent_root_by_default():
    client = _FakeClient()
    fs = _fs(client)
    entries = await fs.ls()
    assert [e.path for e in entries] == ["deck.pptx"]
    assert client.calls[-1] == ("list", "teams/acme/agents/inst-7/users/u-1", "tok")


@pytest.mark.asyncio
async def test_delete_resolves_owned_path():
    client = _FakeClient()
    fs = _fs(client)
    await fs.delete("outputs/x.txt")
    assert client.calls[-1] == (
        "delete",
        "teams/acme/agents/inst-7/users/u-1/outputs/x.txt",
        "tok",
    )


# ---- write/delete isolation: agents mutate only their own subtree (G2/G3) ----


@pytest.mark.asyncio
async def test_write_rejects_shared_path():
    # G3: an agent cannot write into Espace d'equipe even though it can read it.
    fs = _fs()
    with pytest.raises(PermissionError, match="own space"):
        await fs.write("shared/templates/brand.pptx", b"x")


@pytest.mark.asyncio
async def test_delete_rejects_shared_path():
    fs = _fs()
    with pytest.raises(PermissionError, match="own space"):
        await fs.delete("shared/x.txt")


@pytest.mark.asyncio
async def test_write_rejects_sibling_agent_absolute_path():
    # G2: an absolute path into another agent instance's subtree is rejected.
    fs = _fs()
    with pytest.raises(PermissionError, match="own space"):
        await fs.write("/teams/acme/agents/inst-OTHER/users/u-1/outputs/x.pptx", b"x")


@pytest.mark.asyncio
async def test_write_rejects_cross_user_absolute_path():
    fs = _fs()
    with pytest.raises(PermissionError, match="own space"):
        await fs.write("/teams/acme/agents/inst-7/users/u-OTHER/outputs/x.pptx", b"x")


@pytest.mark.asyncio
async def test_link_for_resolves_and_returns_signed_artifact():
    client = _FakeClient()
    fs = _fs(client)
    artifact = await fs.link_for("uploads/report.xlsx")
    assert isinstance(artifact, PublishedArtifact)
    assert artifact.file_name == "report.xlsx"
    assert (
        artifact.href
        == "/dl/teams/acme/agents/inst-7/users/u-1/uploads/report.xlsx?token=sig"
    )
    assert artifact.mime == "application/octet-stream"
    assert client.calls[-1] == (
        "share",
        "teams/acme/agents/inst-7/users/u-1/uploads/report.xlsx",
        "tok",
    )
