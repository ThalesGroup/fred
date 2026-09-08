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

"""`open_document_from_file` tests: a file already on disk becomes the document.

Same fake-store substitution as `test_write_document_tool.py`; the session
workspace root is redirected to a `tmp_path` so no real `~/.fred` is touched.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from fred_capability_session_workspace import capability as workspace_module
from fred_capability_session_workspace import session_workspace_root
from fred_capability_writable_document import store as store_module
from fred_capability_writable_document.capability import (
    WritableDocumentPart,
    _WritableDocumentMiddleware,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.runtime import RuntimeServices
from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union
from langchain_core.tools import StructuredTool
from port_fakes import FakeWritableDocumentStore


@pytest.fixture(autouse=True)
def _ui_part_union() -> None:
    # The chat part reaches `UiPart` only through capability registration; this
    # file exercises the tool without booting a registry.
    rebuild_ui_part_union([WritableDocumentPart])


@pytest.fixture()
def fake_store() -> Iterator[FakeWritableDocumentStore]:
    fake = FakeWritableDocumentStore()
    store_module.set_store_provider(lambda: fake)
    try:
        yield fake
    finally:
        store_module.clear_store_provider()


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(workspace_module, "_SESSIONS_ROOT", tmp_path / "sessions")
    return session_workspace_root("s-1")


def _call(name: str) -> Callable[..., Awaitable[tuple[str, ToolInvocationResult]]]:
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    middleware = _WritableDocumentMiddleware(ctx)
    found = next(t for t in middleware.tools if t.name == name)
    return cast(
        Callable[..., Awaitable[tuple[str, ToolInvocationResult]]],
        cast(StructuredTool, found).coroutine,
    )


@pytest.mark.asyncio
async def test_opens_the_file_content_as_a_document(
    fake_store: FakeWritableDocumentStore, workspace: Path
):
    (workspace / "merged.md").write_text("# Merged\n\nBody", encoding="utf-8")

    content, artifact = await _call("open_document_from_file")(
        path="merged.md", title="Merged report"
    )

    assert "saved (id=" in content
    part = artifact.ui_parts[0]
    assert isinstance(part, WritableDocumentPart)
    assert part.title == "Merged report"
    assert part.content_md == "# Merged\n\nBody"
    rows = await fake_store.list_for_session("s-1")
    assert len(rows) == 1
    assert rows[0].content_md == "# Merged\n\nBody"


@pytest.mark.asyncio
async def test_shares_the_title_dedup_with_write_document(
    fake_store: FakeWritableDocumentStore, workspace: Path
):
    (workspace / "merged.md").write_text("v2", encoding="utf-8")
    _c1, a1 = await _call("write_document")(title="Doc", content_markdown="v1")

    _c2, a2 = await _call("open_document_from_file")(path="merged.md", title="Doc")

    first = cast(WritableDocumentPart, a1.ui_parts[0])
    second = cast(WritableDocumentPart, a2.ui_parts[0])
    assert second.document_id == first.document_id
    assert len(await fake_store.list_for_session("s-1")) == 1


@pytest.mark.asyncio
async def test_missing_file_is_an_error_and_saves_nothing(
    fake_store: FakeWritableDocumentStore, workspace: Path
):
    content, artifact = await _call("open_document_from_file")(
        path="gone.md", title="X"
    )

    assert artifact.is_error is True
    assert "gone.md" in content
    assert await fake_store.list_for_session("s-1") == []


@pytest.mark.asyncio
async def test_path_escaping_the_workspace_is_refused(
    fake_store: FakeWritableDocumentStore, workspace: Path
):
    (workspace.parent / "secret.md").write_text("secret", encoding="utf-8")

    _content, artifact = await _call("open_document_from_file")(
        path="../secret.md", title="X"
    )

    assert artifact.is_error is True
    assert await fake_store.list_for_session("s-1") == []
