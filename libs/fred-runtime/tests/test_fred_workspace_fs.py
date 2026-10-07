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


"""Tests for FredWorkspaceFs path relativization and operations (FILES-04)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_runtime.common.kf_workspace_client import (
    UserStorageUploadResult,
)
from fred_runtime.integrations.v2_runtime.adapters import FredWorkspaceFs
from fred_sdk.contracts.context import PublishedArtifact


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def fs_upload(self, path, content, filename, content_type):
        self.calls.append(("upload", path, content, filename, content_type))
        return UserStorageUploadResult(
            key=path, file_name=filename, size=len(content), download_url=f"/dl/{path}"
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
    fs._credentials = None  # type: ignore[assignment]
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


def test_resolve_absolute_other_team_is_rejected():
    with pytest.raises(PermissionError, match="not the session team"):
        _fs()._resolve("/teams/edf/shared/x")


def test_resolve_rejects_parent_segments():
    with pytest.raises(ValueError, match="parent path segments"):
        _fs()._resolve("outputs/../../etc/secret")


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
async def test_write_rejects_shared_path():
    # Retired team-shared paths are not accepted for capability output writes.
    fs = _fs()
    with pytest.raises(PermissionError, match="retired"):
        await fs.write("shared/templates/brand.pptx", b"x")


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
