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

"""`concat_files` tests: the mechanical merge of sub-agent outputs.

The session root is redirected to a `tmp_path`, so the whole path runs offline
against real files without touching `~/.fred`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from fred_capability_session_workspace import capability as capability_module
from fred_capability_session_workspace.capability import (
    SessionWorkspaceCapability,
    session_workspace_root,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.tools import StructuredTool


@pytest.fixture()
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(capability_module, "_SESSIONS_ROOT", tmp_path / "sessions")
    return session_workspace_root("s-1")


async def _merge(**kwargs: Any) -> tuple[str, ToolInvocationResult]:
    """Call `concat_files` for the default session, exactly as the runtime would."""

    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    middleware = SessionWorkspaceCapability().middleware(ctx)
    # The merge middleware is the capability's own, after deepagents' filesystem one.
    merge_tool = cast(StructuredTool, middleware[-1].tools[0])
    coroutine = cast(
        Callable[..., Awaitable[tuple[str, ToolInvocationResult]]], merge_tool.coroutine
    )
    return await coroutine(**kwargs)


def test_session_workspace_root_is_created(root: Path):
    assert root.is_dir()
    assert root.name == "s-1"


def test_no_session_contributes_no_middleware(root: Path):
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id=None),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    assert SessionWorkspaceCapability().middleware(ctx) == []


@pytest.mark.asyncio
async def test_merge_preserves_order_and_adds_headings(root: Path):
    (root / "part-1.md").write_text("first body", encoding="utf-8")
    (root / "part-2.md").write_text("second body", encoding="utf-8")

    content, artifact = await _merge(
        paths=["part-2.md", "part-1.md"], output_path="merged.md"
    )

    assert artifact.is_error is False
    assert "2 file(s)" in content
    merged = (root / "merged.md").read_text(encoding="utf-8")
    assert merged == "## part 2\n\nsecond body\n\n## part 1\n\nfirst body"


@pytest.mark.asyncio
async def test_merge_without_headings(root: Path):
    (root / "a.md").write_text("A", encoding="utf-8")
    (root / "b.md").write_text("B", encoding="utf-8")

    await _merge(paths=["a.md", "b.md"], output_path="out.md", heading_per_file=False)

    assert (root / "out.md").read_text(encoding="utf-8") == "A\n\nB"


@pytest.mark.asyncio
async def test_missing_file_errors_and_writes_nothing(root: Path):
    (root / "a.md").write_text("A", encoding="utf-8")

    content, artifact = await _merge(paths=["a.md", "gone.md"], output_path="out.md")

    assert artifact.is_error is True
    assert "gone.md" in content
    assert not (root / "out.md").exists()


@pytest.mark.asyncio
async def test_path_escaping_the_workspace_is_refused(root: Path):
    outside = root.parent / "secret.md"
    outside.write_text("secret", encoding="utf-8")

    content, artifact = await _merge(paths=["../secret.md"], output_path="out.md")

    assert artifact.is_error is True
    assert "outside the session workspace" in content
    assert not (root / "out.md").exists()


@pytest.mark.asyncio
async def test_output_path_escaping_the_workspace_is_refused(root: Path):
    (root / "a.md").write_text("A", encoding="utf-8")

    _content, artifact = await _merge(paths=["a.md"], output_path="../escaped.md")

    assert artifact.is_error is True
    assert not (root.parent / "escaped.md").exists()


@pytest.mark.asyncio
async def test_empty_path_list_errors(root: Path):
    _content, artifact = await _merge(paths=[], output_path="out.md")

    assert artifact.is_error is True
