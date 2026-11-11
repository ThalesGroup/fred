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

"""The separately enabled demo importer reuses the existing document editor."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fred_capability_writable_document import store as store_module
from fred_capability_writable_document.capability import (
    WritableDocumentCapability,
    WritableDocumentPart,
)
from fred_capability_writable_document.open_capability import (
    OpenWritableDocumentCapability,
)
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolFailure, ToolFailureCode
from fred_sdk.contracts.runtime import (
    ConversationFilesystemPermissionError,
    ConversationFilesystemPort,
    ConversationScratchpadInvalidPathError,
    RuntimeServices,
)
from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union
from langchain_core.tools import StructuredTool
from port_fakes import FakeWritableDocumentStore


@pytest.fixture()
def fake_store():
    rebuild_ui_part_union([WritableDocumentPart])
    store = FakeWritableDocumentStore()
    store_module.set_store_provider(lambda: store)
    try:
        yield store
    finally:
        store_module.clear_store_provider()
        rebuild_ui_part_union()


def _tool(filesystem: ConversationFilesystemPort | None) -> StructuredTool:
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="user-1", session_id="session-1"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(conversation_filesystem=filesystem),
    )
    result = OpenWritableDocumentCapability().tools(ctx)[0]
    assert isinstance(result, StructuredTool)
    return result


async def _run_tool(
    filesystem: ConversationFilesystemPort | None, *, path: str, title: str
):
    coroutine = _tool(filesystem).coroutine
    assert coroutine is not None
    return await coroutine(path=path, title=title)


@pytest.mark.asyncio
async def test_imports_markdown_without_exposing_its_body_to_the_model(fake_store):
    registry = CapabilityRegistry()
    registry.register(WritableDocumentCapability())
    registry.register(OpenWritableDocumentCapability())
    registry.validate({})

    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    filesystem.read_text.return_value = "# Report\n\nComplete result"
    result, artifact = await _run_tool(
        filesystem, path="/.deep/results/merged.md", title="Merged report"
    )

    filesystem.read_text.assert_awaited_once_with(
        "/.deep/results/merged.md", origin="agent"
    )
    assert "Complete result" not in result
    assert not artifact.is_error
    part = artifact.ui_parts[0]
    assert isinstance(part, WritableDocumentPart)
    assert part.content_md == "# Report\n\nComplete result"
    rows = await fake_store.list_for_session("session-1")
    assert len(rows) == 1
    assert rows[0].user_id == "user-1"


@pytest.mark.asyncio
async def test_rejects_non_markdown_before_reading(fake_store):
    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    _result, artifact = await _run_tool(filesystem, path="/results.csv", title="Report")

    assert artifact.failure == ToolFailure(code=ToolFailureCode.invalid_arguments)
    filesystem.read_text.assert_not_awaited()
    assert await fake_store.list_for_session("session-1") == []


@pytest.mark.asyncio
async def test_imported_nul_markdown_is_cleaned_and_saved(fake_store):
    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    filesystem.read_text.return_value = "# Report\n\nInvalid\x00text"

    content, artifact = await _run_tool(filesystem, path="/report.md", title="Report")

    assert not artifact.is_error and artifact.blocks[0].text == content
    assert "content_markdown: 1" in content
    assert artifact.ui_parts[0].content_md == "# Report\n\nInvalidtext"
    rows = await fake_store.list_for_session("session-1")
    assert len(rows) == 1 and rows[0].content_md == artifact.ui_parts[0].content_md


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "error", "code"),
    [
        (
            "report.md",
            ConversationScratchpadInvalidPathError("Absolute path required"),
            ToolFailureCode.invalid_arguments,
        ),
        (
            "/../secret.md",
            ConversationScratchpadInvalidPathError("Unsafe path"),
            ToolFailureCode.invalid_arguments,
        ),
        (
            "/mounted/private.md",
            ConversationFilesystemPermissionError("Access denied"),
            ToolFailureCode.resource_unavailable,
        ),
    ],
)
async def test_respects_filesystem_path_and_permission_checks(
    fake_store, path, error, code
):
    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    filesystem.read_text.side_effect = error
    _result, artifact = await _run_tool(filesystem, path=path, title="Report")

    filesystem.read_text.assert_awaited_once_with(path, origin="agent")
    assert artifact.failure == ToolFailure(code=code)
    assert await fake_store.list_for_session("session-1") == []


@pytest.mark.asyncio
async def test_requires_filesystem(fake_store):
    _result, unavailable = await _run_tool(None, path="/report.md", title="Report")
    assert unavailable.failure == ToolFailure(code=ToolFailureCode.resource_unavailable)

    assert await fake_store.list_for_session("session-1") == []


@pytest.mark.asyncio
async def test_import_does_not_add_a_demo_size_limit(fake_store):
    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    content = "x" * (1024 * 1024 + 1)
    filesystem.read_text.return_value = content

    _result, artifact = await _run_tool(filesystem, path="/report.md", title="Report")

    assert not artifact.is_error
    rows = await fake_store.list_for_session("session-1")
    assert rows[0].content_md == content
