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

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_sdk.contracts.runtime import ConversationScratchpadFileNotFoundError
from fred_sdk.contracts.runtime import (
    ConversationScratchpadEditConflictError,
    ConversationScratchpadInvalidPathError,
    ConversationScratchpadQuotaExceededError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.app import ConversationFilesystemQuotaConfig


class _MemoryFilesystem:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def read(self, path: str) -> bytes:
        try:
            return self.files[path]
        except KeyError as exc:
            raise FileNotFoundError(path) from exc

    async def write(self, path: str, data: bytes | str) -> None:
        self.files[path] = data.encode() if isinstance(data, str) else data

    async def list(self, prefix: str = "") -> list[FilesystemResourceInfoResult]:
        return [
            FilesystemResourceInfoResult(
                path=path,
                size=len(content),
                type=FilesystemResourceInfo.FILE,
                modified=datetime.now(),
            )
            for path, content in self.files.items()
            if path.startswith(prefix)
        ]

    async def delete(self, path: str) -> None:
        self.files.pop(path, None)
        for candidate in tuple(self.files):
            if candidate.startswith(f"{path.rstrip('/')}/"):
                del self.files[candidate]

    async def mkdir(self, path: str) -> None:
        del path

    async def exists(self, path: str) -> bool:
        return path in self.files or any(
            candidate.startswith(f"{path.rstrip('/')}/") for candidate in self.files
        )


def _quotas(
    *,
    scratchpad_max_bytes: int = 100,
    scratchpad_max_files: int = 10,
    deep_max_bytes: int = 100,
    deep_max_files: int = 10,
) -> ConversationFilesystemQuotaConfig:
    return ConversationFilesystemQuotaConfig(
        scratchpad_max_bytes=scratchpad_max_bytes,
        scratchpad_max_files=scratchpad_max_files,
        deep_max_bytes=deep_max_bytes,
        deep_max_files=deep_max_files,
    )


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.counts: list[tuple[str, dict[str, str | None]]] = []

    def count(self, name, inc=1, *, dims=None, labels=None, actor) -> None:
        del inc, labels, actor
        self.counts.append((name, dict(dims or {})))


@pytest.mark.asyncio
async def test_scratchpad_bindings_share_one_conversation_but_isolate_another() -> None:
    storage = _MemoryFilesystem()
    first = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    same_conversation = ConversationFilesystemService(
        storage, "conversation-a"
    ).scratchpad()
    other_conversation = ConversationFilesystemService(
        storage, "conversation-b"
    ).scratchpad()

    await first.write_text("research/notes.md", "shared result")

    assert await same_conversation.read_text("research/notes.md") == "shared result"
    with pytest.raises(ConversationScratchpadFileNotFoundError):
        await other_conversation.read_text("research/notes.md")
    assert storage.files == {
        "conversations/conversation-a/scratchpad/research/notes.md": b"shared result"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    (
        "/absolute.md",
        ".deep/internal.md",
        "../outside.md",
        "folder/../outside.md",
        "folder/./note.md",
        "folder//note.md",
        "folder\\note.md",
        "folder/",
    ),
)
async def test_scratchpad_rejects_unsafe_paths_before_storage(path: str) -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()

    with pytest.raises(ConversationScratchpadInvalidPathError):
        await scratchpad.write_text(path, "must not be stored")

    assert storage.files == {}


@pytest.mark.asyncio
async def test_scratchpad_rejects_non_text_before_storage() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()

    with pytest.raises(ConversationScratchpadUnsupportedContentError):
        await scratchpad.write_text("binary.dat", b"\xff")  # type: ignore[arg-type]

    assert storage.files == {}


@pytest.mark.parametrize("session_id", ("", ".", "..", "a/b", "a\\b", "a b"))
def test_conversation_binding_rejects_unsafe_session_identifiers(
    session_id: str,
) -> None:
    with pytest.raises(ConversationScratchpadInvalidPathError):
        ConversationFilesystemService(_MemoryFilesystem(), session_id)


@pytest.mark.asyncio
async def test_stale_edit_preserves_latest_content() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    await scratchpad.write_text("notes.md", "latest content")

    with pytest.raises(ConversationScratchpadEditConflictError):
        await scratchpad.edit_text("notes.md", "earlier content", "replacement")

    assert await scratchpad.read_text("notes.md") == "latest content"


@pytest.mark.asyncio
async def test_full_write_replaces_and_edit_uses_latest_content() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    await scratchpad.write_text("notes.md", "first draft")
    await scratchpad.write_text("notes.md", "second draft")

    match_count = await scratchpad.edit_text("notes.md", "second", "final")

    assert match_count == 1
    assert await scratchpad.read_text("notes.md") == "final draft"


@pytest.mark.asyncio
async def test_edit_requires_unique_match_unless_replace_all_is_explicit() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    await scratchpad.write_text("notes.md", "same and same")

    with pytest.raises(ConversationScratchpadEditConflictError):
        await scratchpad.edit_text("notes.md", "same", "changed")
    assert await scratchpad.read_text("notes.md") == "same and same"

    match_count = await scratchpad.edit_text(
        "notes.md", "same", "changed", replace_all=True
    )

    assert match_count == 2
    assert await scratchpad.read_text("notes.md") == "changed and changed"


@pytest.mark.asyncio
async def test_list_exists_and_delete_use_scratchpad_relative_paths() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    await scratchpad.write_text("research/one.md", "one")
    await scratchpad.write_text("research/two.md", "two")
    await scratchpad.write_text("other.md", "other")

    assert await scratchpad.list("research") == (
        "research/one.md",
        "research/two.md",
    )
    assert await scratchpad.exists("research/one.md") is True

    await scratchpad.delete("research/one.md")
    await scratchpad.delete("research/missing.md")

    assert await scratchpad.exists("research/one.md") is False
    assert await scratchpad.list() == ("other.md", "research/two.md")


@pytest.mark.asyncio
async def test_storage_failure_uses_stable_content_free_domain_error() -> None:
    class _FailingFilesystem(_MemoryFilesystem):
        async def write(self, path: str, data: bytes | str) -> None:
            del path, data
            raise RuntimeError("provider leaked secret and file content")

    scratchpad = ConversationFilesystemService(
        _FailingFilesystem(), "conversation-a"
    ).scratchpad()

    with pytest.raises(
        ConversationScratchpadStorageError,
        match="^Shared scratchpad storage failed$",
    ):
        await scratchpad.write_text("notes.md", "private content")


@pytest.mark.asyncio
async def test_scratchpad_rejects_byte_quota_before_mutating_storage() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_bytes=5),
    ).scratchpad()

    with pytest.raises(ConversationScratchpadQuotaExceededError) as error:
        await scratchpad.write_text("notes.md", "123456")

    assert error.value.resource == "bytes"
    assert error.value.limit == 5
    assert error.value.attempted == 6
    assert storage.files == {}


@pytest.mark.asyncio
async def test_scratchpad_rejects_file_count_quota_before_mutating_storage() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_files=1),
    ).scratchpad()
    await scratchpad.write_text("one.md", "1")

    with pytest.raises(ConversationScratchpadQuotaExceededError) as error:
        await scratchpad.write_text("two.md", "2")

    assert error.value.resource == "files"
    assert error.value.limit == 1
    assert error.value.attempted == 2
    assert storage.files == {
        "conversations/conversation-a/scratchpad/one.md": b"1"
    }


@pytest.mark.asyncio
async def test_one_file_can_consume_all_remaining_byte_budget() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_bytes=10),
    ).scratchpad()
    await scratchpad.write_text("first.md", "123")

    await scratchpad.write_text("remaining.md", "1234567")

    assert await scratchpad.read_text("remaining.md") == "1234567"


@pytest.mark.asyncio
async def test_first_mutation_recounts_existing_storage() -> None:
    storage = _MemoryFilesystem()
    storage.files = {
        "conversations/conversation-a/scratchpad/existing.md": b"12345"
    }
    scratchpad = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_bytes=5),
    ).scratchpad()

    with pytest.raises(ConversationScratchpadQuotaExceededError):
        await scratchpad.write_text("new.md", "1")

    assert storage.files == {
        "conversations/conversation-a/scratchpad/existing.md": b"12345"
    }


@pytest.mark.asyncio
async def test_replacement_uses_size_delta_instead_of_double_counting() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_bytes=5),
    ).scratchpad()
    await scratchpad.write_text("notes.md", "12345")

    await scratchpad.write_text("notes.md", "1")
    await scratchpad.write_text("other.md", "2345")

    assert await scratchpad.read_text("notes.md") == "1"
    assert await scratchpad.read_text("other.md") == "2345"


@pytest.mark.asyncio
async def test_delete_and_purge_release_accounted_quota() -> None:
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_files=1),
    )
    scratchpad = service.scratchpad()
    await scratchpad.write_text("one.md", "1")
    await scratchpad.delete("one.md")
    await scratchpad.write_text("two.md", "2")

    await scratchpad.purge()  # type: ignore[attr-defined]
    await scratchpad.write_text("three.md", "3")

    assert await scratchpad.list() == ("three.md",)


@pytest.mark.asyncio
async def test_same_process_mutations_are_serialized_before_quota_check() -> None:
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_files=1),
    )
    first = service.scratchpad()
    second = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_files=1),
    ).scratchpad()

    results = await asyncio.gather(
        first.write_text("one.md", "1"),
        second.write_text("two.md", "2"),
        return_exceptions=True,
    )

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, ConversationScratchpadQuotaExceededError) for result in results) == 1
    assert len(storage.files) == 1


@pytest.mark.asyncio
async def test_scratchpad_and_deep_namespace_quotas_are_independent() -> None:
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_bytes=3, deep_max_bytes=4),
    )
    scratchpad = service.scratchpad()
    deep = service.namespace(".deep")

    await scratchpad.write_text("notes.md", "123")
    await deep.write_text("state.txt", "1234")

    with pytest.raises(ConversationScratchpadQuotaExceededError):
        await scratchpad.write_text("extra.md", "1")
    with pytest.raises(ConversationScratchpadQuotaExceededError):
        await deep.write_text("extra.md", "1")


@pytest.mark.asyncio
async def test_quota_observability_has_only_bounded_content_free_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = _MemoryFilesystem()
    kpi = _RecordingKPIWriter()
    scratchpad = ConversationFilesystemService(
        storage,
        "private-conversation",
        quotas=_quotas(scratchpad_max_bytes=1),
        kpi=kpi,
    ).scratchpad()

    with caplog.at_level("INFO"), pytest.raises(
        ConversationScratchpadQuotaExceededError
    ):
        await scratchpad.write_text("private-path.md", "private-content")

    assert kpi.counts == [
        (
            "conversation.filesystem.quota_rejected_total",
            {
                "conversation_fs_namespace": "scratchpad",
                "conversation_fs_resource": "bytes",
            },
        )
    ]
    assert all("private-content" not in record.getMessage() for record in caplog.records)
    assert all("private-path.md" not in record.getMessage() for record in caplog.records)
    assert all(
        "private-conversation" not in record.getMessage() for record in caplog.records
    )
    usage = next(
        record.conversation_filesystem
        for record in caplog.records
        if record.getMessage() == "Conversation filesystem namespace usage"
    )
    assert usage == {
        "namespace": "scratchpad",
        "usage_bytes": 0,
        "usage_files": 0,
    }
