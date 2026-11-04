# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Capability binaries share the conversation namespace and deletion lifecycle."""

from types import SimpleNamespace
from typing import cast

import pytest
from fred_core.filesystem.structures import BaseFilesystem
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.integrations.v2_runtime import adapters
from fred_runtime.integrations.v2_runtime.adapters import FredWorkspaceFs
from fred_runtime.runtime_context import RuntimeConfig, RuntimeContext
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import ConversationScratchpadInvalidPathError
from test_conversation_filesystem import _MemoryFilesystem


def _writer(session_id: str | None = "one"):
    return FredWorkspaceFs(
        binding=cast(
            BoundRuntimeContext,
            SimpleNamespace(runtime_context=SimpleNamespace(session_id=session_id)),
        ),
    )


@pytest.fixture
def storage(monkeypatch):
    storage = _MemoryFilesystem()
    runtime = RuntimeContext(
        RuntimeConfig(
            knowledge_flow_url="https://unused.invalid",
            filesystem=cast(BaseFilesystem, storage),
            api_base_url="/pod/v1",
        )
    )
    monkeypatch.setattr(adapters, "get_runtime_context", lambda: runtime)
    return storage


@pytest.mark.asyncio
async def test_binary_outputs_are_scoped_and_whole_conversation_purge_removes_them(
    storage,
):
    artifact = await _writer().write(
        "outputs/one/Quarter 1.pptx",
        b"\x00\xff",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert artifact.key == "conversations/one/exports/Quarter 1.pptx"
    assert (
        artifact.href
        == "/pod/v1/agents/sessions/one/filesystem/exports/Quarter%201.pptx"
    )
    assert artifact.size == 2
    assert artifact.file_name == "Quarter 1.pptx"
    await _writer("other").write("outputs/other/deck.pptx", b"retained")
    await ConversationFilesystemService(storage, "one").purge()
    assert storage.files == {"conversations/other/exports/deck.pptx": b"retained"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "outputs/other/deck.pptx",
        "shared/deck.pptx",
        "/teams/t/outputs/one/deck.pptx",
        "outputs/deck.pptx",
    ],
)
async def test_outputs_cannot_choose_a_different_owner(storage, path):
    with pytest.raises(PermissionError):
        await _writer().write(path, b"secret")
    assert storage.files == {}


@pytest.mark.asyncio
async def test_outputs_reject_traversal_and_missing_session(storage):
    with pytest.raises(ConversationScratchpadInvalidPathError):
        await _writer().write("outputs/one/../../other/secret", b"secret")
    with pytest.raises(RuntimeError, match="conversation"):
        await _writer(None).write("outputs/deck.pptx", b"secret")
    assert storage.files == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias",
    [
        "AABBCCDD-1111-4222-8333-0123456789AB",
        "aabbccdd1111422283330123456789ab",  # pragma: allowlist secret - synthetic UUID alias
        "{AABBCCDD-1111-4222-8333-0123456789AB}",
    ],
)
async def test_published_artifact_uses_canonical_conversation_identity(storage, alias):
    canonical = "aabbccdd-1111-4222-8333-0123456789ab"
    artifact = await _writer(alias).write(f"outputs/{alias}/deck.pptx", b"private")
    assert artifact.key == f"conversations/{canonical}/exports/deck.pptx"
    assert (
        artifact.href
        == f"/pod/v1/agents/sessions/{canonical}/filesystem/exports/deck.pptx"
    )
    assert storage.files == {artifact.key: b"private"}
    await ConversationFilesystemService(storage, canonical).purge()
    assert storage.files == {}
