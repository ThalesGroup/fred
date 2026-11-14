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
from fred_runtime.app import ConversationFilesystemQuotaConfig
from fred_runtime.conversation_filesystem import (
    _FILESYSTEM_WRITES,
    ConversationFilesystemService,
    ConversationTextNamespacePort,
)
from fred_sdk.contracts.runtime import (
    ConversationScratchpadEditConflictError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadInvalidPathError,
    ConversationScratchpadQuotaExceededError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)


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
async def test_physical_namespace_allows_safe_deep_named_subdirectory() -> None:
    storage = _MemoryFilesystem()
    namespace = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    await namespace.write_text(".deep/internal.md", "trusted")
    assert await namespace.read_text(".deep/internal.md") == "trusted"


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
    assert storage.files == {"conversations/conversation-a/scratchpad/one.md": b"1"}


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
    storage.files = {"conversations/conversation-a/scratchpad/existing.md": b"12345"}
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
async def test_purge_deletes_without_recounting_namespace_first() -> None:
    class _CountingFilesystem(_MemoryFilesystem):
        def __init__(self) -> None:
            super().__init__()
            self.list_calls = 0

        async def list(self, prefix: str = "") -> list[FilesystemResourceInfoResult]:
            self.list_calls += 1
            return await super().list(prefix)

    storage = _CountingFilesystem()
    storage.files = {"conversations/conversation-a/scratchpad/existing.md": b"existing"}
    scratchpad = ConversationFilesystemService(storage, "conversation-a").scratchpad()

    await scratchpad.purge()  # type: ignore[attr-defined]

    assert storage.list_calls == 0
    assert storage.files == {}


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
    assert (
        sum(
            isinstance(result, ConversationScratchpadQuotaExceededError)
            for result in results
        )
        == 1
    )
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
    deep = service.namespace(".deep", max_bytes=4, max_files=10000)

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

    with (
        caplog.at_level("INFO"),
        pytest.raises(ConversationScratchpadQuotaExceededError),
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
    assert all(
        "private-content" not in record.getMessage() for record in caplog.records
    )
    assert all(
        "private-path.md" not in record.getMessage() for record in caplog.records
    )
    assert all(
        "private-conversation" not in record.getMessage() for record in caplog.records
    )
    usage = next(
        getattr(record, "conversation_filesystem")
        for record in caplog.records
        if record.getMessage() == "Conversation filesystem namespace usage"
    )
    assert usage == {
        "conversation_id": "private-conversation",
        "namespace": "scratchpad",
        "usage_bytes": 0,
        "usage_files": 0,
    }
    rejection = next(
        getattr(record, "conversation_filesystem")
        for record in caplog.records
        if record.getMessage() == "Conversation filesystem quota rejected mutation"
    )
    assert rejection["conversation_id"] == "private-conversation"


@pytest.mark.asyncio
async def test_storage_failure_log_has_safe_operation_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FailingFilesystem(_MemoryFilesystem):
        async def write(self, path: str, data: bytes | str) -> None:
            del path, data
            raise RuntimeError("provider credential and private-content")

    scratchpad = ConversationFilesystemService(
        _FailingFilesystem(), "private-conversation"
    ).scratchpad()

    with caplog.at_level("WARNING"), pytest.raises(ConversationScratchpadStorageError):
        await scratchpad.write_text("private-path.md", "private-content")

    failure = next(
        getattr(record, "conversation_filesystem")
        for record in caplog.records
        if record.getMessage() == "Conversation filesystem storage operation failed"
    )
    assert failure == {
        "conversation_id": "private-conversation",
        "operation": "write",
        "namespace": "scratchpad",
        "error_category": "RuntimeError",
    }
    assert "private-content" not in caplog.text
    assert "private-path.md" not in caplog.text
    assert "provider credential" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias",
    [
        "AABBCCDD-1111-4222-8333-0123456789AB",
        "aabbccdd1111422283330123456789ab",  # pragma: allowlist secret - synthetic UUID alias
        "{AABBCCDD-1111-4222-8333-0123456789AB}",
        "urn:uuid:aabbccdd-1111-4222-8333-0123456789ab",
    ],
)
async def test_uuid_aliases_share_physical_identity_and_purge(alias):
    canonical = "aabbccdd-1111-4222-8333-0123456789ab"
    storage = _MemoryFilesystem()
    writer = ConversationFilesystemService(storage, alias)
    reader = ConversationFilesystemService(storage, canonical)
    assert writer.session_id == canonical
    await writer.scratchpad().write_text("note", "private")
    await reader.namespace("deep", max_bytes=1024, max_files=10).write_bytes(
        "deck.pptx", b"generated"
    )
    assert await reader.scratchpad().read_text("note") == "private"
    assert (
        await writer.namespace("deep", max_bytes=1024, max_files=10).read_bytes(
            "deck.pptx"
        )
        == b"generated"
    )
    other = ConversationFilesystemService(storage, canonical + "-neighbour")
    await other.scratchpad().write_text("note", "retained")
    await reader.purge()
    assert storage.files == {
        f"conversations/{canonical}-neighbour/scratchpad/note": b"retained"
    }
    await reader.scratchpad().write_text("again", "private")
    await writer.purge()
    assert await other.scratchpad().read_text("note") == "retained"
    assert not await reader.scratchpad().exists("again")


type NamespacePair = tuple[
    _MemoryFilesystem,
    ConversationFilesystemService,
    ConversationTextNamespacePort,
    ConversationTextNamespacePort,
]


@pytest.fixture(params=("scratchpad", ".deep"))
def independent_namespaces(request: pytest.FixtureRequest) -> NamespacePair:
    # Distinct clients emulate separate processes over the same object store.
    # Two services using one client would share the process-local lock/cache.
    first_storage, second_storage = _MemoryFilesystem(), _MemoryFilesystem()
    second_storage.files = first_storage.files
    first_service = ConversationFilesystemService(first_storage, "conversation-a")
    second_service = ConversationFilesystemService(second_storage, "conversation-a")
    first = first_service.namespace(request.param, max_bytes=100, max_files=3)
    second = second_service.namespace(request.param, max_bytes=100, max_files=3)
    return first_storage, second_service, first, second


@pytest.mark.asyncio
async def test_remote_addition_is_counted_before_byte_quota_refusal(
    independent_namespaces: NamespacePair,
) -> None:
    storage, _, first, second = independent_namespaces
    await first.write_bytes("a", b"x" * 40)
    await second.write_bytes("b", b"x" * 40)
    before = dict(storage.files)

    with pytest.raises(ConversationScratchpadQuotaExceededError) as error:
        await first.write_bytes("c", b"x" * 30)

    assert (error.value.resource, error.value.attempted) == ("bytes", 110)
    assert storage.files == before


@pytest.mark.asyncio
async def test_remote_additions_and_replacements_use_current_file_count(
    independent_namespaces: NamespacePair,
) -> None:
    storage, _, first, second = independent_namespaces
    await first.write_text("a", "")
    await second.write_text("b", "")
    await second.write_text("c", "")
    # A remotely created empty file is a replacement, not a fourth file.
    await first.write_text("b", "replacement")
    before = dict(storage.files)

    with pytest.raises(ConversationScratchpadQuotaExceededError) as error:
        await first.write_text("d", "")

    assert (error.value.resource, error.value.attempted) == ("files", 4)
    assert storage.files == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("write", "edit"))
async def test_remote_replacement_growth_and_shrink_are_observed(
    independent_namespaces: NamespacePair,
    operation: str,
) -> None:
    storage, _, first, second = independent_namespaces
    await first.write_text("a", "x" * 40)
    await first.write_text("b", "x" * 40)
    await second.write_text("b", "x" * 60)

    async def replace(size: int) -> None:
        if operation == "write":
            await first.write_text("a", "x" * size)
        else:
            assert await first.edit_text("a", "x" * 40, "x" * size) == 1

    before = dict(storage.files)
    with pytest.raises(ConversationScratchpadQuotaExceededError) as error:
        await replace(50)
    assert (error.value.resource, error.value.attempted) == ("bytes", 110)
    assert storage.files == before

    await second.write_text("b", "x" * 10)
    await replace(90)
    assert len(storage.files) == 2
    assert sum(map(len, storage.files.values())) == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("removal", ("file", "directory", "namespace", "conversation"))
async def test_remote_removal_releases_bytes_and_file_budget(
    independent_namespaces: NamespacePair,
    removal: str,
) -> None:
    storage, second_service, first, second = independent_namespaces
    await first.write_text("folder/a", "x" * 100)
    await first.write_text("folder/b", "")
    await first.write_text("folder/c", "")
    if removal == "file":
        await second.delete("folder/a")
    elif removal == "directory":
        await second.delete("folder")
    elif removal == "namespace":
        await second.purge()
    else:
        await second_service.purge()

    await first.write_bytes("new", b"x" * 100)
    assert sum(map(len, storage.files.values())) == 100
    assert len(storage.files) == (3 if removal == "file" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("list", "missing_size_read"))
async def test_recount_failure_after_success_never_uses_empty_or_previous_usage(
    independent_namespaces: NamespacePair,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    storage, _, first, second = independent_namespaces
    await first.write_text("a", "x" * 40)
    await second.write_text("b", "x" * 40)
    before = dict(storage.files)
    original_list = storage.list

    async def failing_list(prefix: str = "") -> list[FilesystemResourceInfoResult]:
        entries = await original_list(prefix)
        if failure == "list":
            # The provider can fail after collecting part of a paginated list.
            raise OSError("listing unavailable")
        for entry in entries:
            entry.size = None
        return entries

    async def failing_read(path: str) -> bytes:
        raise OSError("size unavailable")

    monkeypatch.setattr(storage, "list", failing_list)
    monkeypatch.setattr(storage, "read", failing_read)
    with pytest.raises(ConversationScratchpadStorageError):
        await first.write_text("c", "x" * 30)
    assert storage.files == before

    monkeypatch.setattr(storage, "list", original_list)
    with pytest.raises(ConversationScratchpadQuotaExceededError):
        await first.write_text("c", "x" * 30)
    assert storage.files == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("write", "edit", "delete", "purge"))
@pytest.mark.parametrize("namespace_id", ("scratchpad", ".deep"))
async def test_cancelled_mutation_holds_lock_until_storage_finishes(
    operation: str,
    namespace_id: str,
) -> None:
    entered, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class SlowFilesystem(_MemoryFilesystem):
        slow = False

        async def write(self, path: str, data: bytes | str) -> None:
            if self.slow:
                entered.set()
                await release.wait()
            await super().write(path, data)

        async def delete(self, path: str) -> None:
            if self.slow:
                entered.set()
                await release.wait()
            await super().delete(path)

    storage = SlowFilesystem()
    first = ConversationFilesystemService(storage, "conversation-a").namespace(
        namespace_id, max_bytes=5, max_files=1
    )
    second = ConversationFilesystemService(storage, "conversation-a").namespace(
        namespace_id, max_bytes=5, max_files=1
    )
    if operation != "write":
        await first.write_text("a", "x")
    storage.slow = True
    if operation == "write":
        mutation = first.write_text("a", "xxxxx")
    elif operation == "edit":
        mutation = first.edit_text("a", "x", "xxxxx")
    elif operation == "delete":
        mutation = first.delete("a")
    else:
        mutation = first.purge()
    writer = asyncio.create_task(mutation)

    async def next_write() -> None:
        waiting.set()
        await second.write_text("b", "y")

    follower = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        writer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writer
        follower = asyncio.create_task(next_write())
        await asyncio.wait_for(waiting.wait(), timeout=5)
        # The follower reached lock acquisition but cannot start its recount.
        assert not follower.done()
        release.set()
        if operation in {"write", "edit"}:
            with pytest.raises(ConversationScratchpadQuotaExceededError):
                await asyncio.wait_for(follower, timeout=5)
            assert await first.read_text("a") == "xxxxx"
        else:
            await asyncio.wait_for(follower, timeout=5)
            assert await first.list() == ("b",)
    finally:
        release.set()
        await asyncio.gather(
            writer, *([follower] if follower else []), return_exceptions=True
        )
        await asyncio.gather(*tuple(_FILESYSTEM_WRITES), return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_waiter_never_starts_a_deferred_write() -> None:
    entered, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class SlowFilesystem(_MemoryFilesystem):
        async def write(self, path: str, data: bytes | str) -> None:
            entered.set()
            await release.wait()
            await super().write(path, data)

    storage = SlowFilesystem()
    namespace = ConversationFilesystemService(storage, "conversation-a").scratchpad()
    writer = asyncio.create_task(namespace.write_text("a", "first"))

    async def queued_write() -> None:
        waiting.set()
        await namespace.write_text("b", "cancelled")

    follower = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        follower = asyncio.create_task(queued_write())
        await asyncio.wait_for(waiting.wait(), timeout=5)
        follower.cancel()
        with pytest.raises(asyncio.CancelledError):
            await follower
        release.set()
        await asyncio.wait_for(writer, timeout=5)
        assert await namespace.list() == ("a",)
    finally:
        release.set()
        await asyncio.gather(
            writer, *([follower] if follower else []), return_exceptions=True
        )
        await asyncio.gather(*tuple(_FILESYSTEM_WRITES), return_exceptions=True)


@pytest.mark.asyncio
async def test_uncertain_write_is_observed_and_releases_local_lock(
    independent_namespaces: NamespacePair,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, _, first, second = independent_namespaces
    await first.write_bytes("a", b"x" * 40)
    original_write = storage.write

    async def uncertain_write(path: str, data: bytes | str) -> None:
        await original_write(path, data)
        raise TimeoutError("remote result unknown")

    monkeypatch.setattr(storage, "write", uncertain_write)
    with pytest.raises(ConversationScratchpadStorageError):
        await first.write_bytes("b", b"x" * 40)
    monkeypatch.setattr(storage, "write", original_write)

    for namespace in (first, second):
        with pytest.raises(ConversationScratchpadQuotaExceededError) as error:
            await asyncio.wait_for(namespace.write_bytes("c", b"x" * 30), timeout=5)
        assert (error.value.resource, error.value.attempted) == ("bytes", 110)
    await first.delete("b")
    await first.write_bytes("c", b"x" * 60)
