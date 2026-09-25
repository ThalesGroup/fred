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
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import (
    ConversationFilesystemPermissionError,
    ConversationFilesystemPort,
    ConversationScratchpadInvalidPathError,
    RuntimeServices,
)
from fred_runtime.capabilities.registry import CapabilityRegistry
from port_fakes import FakeWritableDocumentStore


@pytest.fixture()
def fake_store():
    store = FakeWritableDocumentStore()
    store_module.set_store_provider(lambda: store)
    try:
        yield store
    finally:
        store_module.clear_store_provider()


def _tool(filesystem: ConversationFilesystemPort | None):
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="user-1", session_id="session-1"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(conversation_filesystem=filesystem),
    )
    return OpenWritableDocumentCapability().tools(ctx)[0]


@pytest.mark.asyncio
async def test_imports_markdown_without_exposing_its_body_to_the_model(fake_store):
    registry = CapabilityRegistry()
    registry.register(WritableDocumentCapability())
    registry.register(OpenWritableDocumentCapability())
    registry.validate({})

    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    filesystem.read_text.return_value = "# Report\n\nComplete result"
    result, artifact = await _tool(filesystem).coroutine(
        path="/.deep/results/merged.md", title="Merged report"
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
@pytest.mark.parametrize(
    "path", ["report.md", "/results.csv"]
)
async def test_rejects_unsupported_paths_before_reading(fake_store, path):
    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    _result, artifact = await _tool(filesystem).coroutine(path=path, title="Report")

    assert artifact.is_error
    filesystem.read_text.assert_not_awaited()
    assert await fake_store.list_for_session("session-1") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("/../secret.md", ConversationScratchpadInvalidPathError("Unsafe path")),
        ("/mounted/private.md", ConversationFilesystemPermissionError("Access denied")),
    ],
)
async def test_respects_filesystem_path_and_permission_checks(fake_store, path, error):
    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    filesystem.read_text.side_effect = error
    _result, artifact = await _tool(filesystem).coroutine(path=path, title="Report")

    filesystem.read_text.assert_awaited_once_with(path, origin="agent")
    assert artifact.is_error
    assert await fake_store.list_for_session("session-1") == []


@pytest.mark.asyncio
async def test_requires_filesystem_and_limits_editor_import(fake_store):
    _result, unavailable = await _tool(None).coroutine(
        path="/report.md", title="Report"
    )
    assert unavailable.is_error

    filesystem = AsyncMock(spec=ConversationFilesystemPort)
    filesystem.read_text.return_value = "x" * (1024 * 1024 + 1)
    _result, oversized = await _tool(filesystem).coroutine(
        path="/report.md", title="Report"
    )
    assert oversized.is_error
    assert await fake_store.list_for_session("session-1") == []
