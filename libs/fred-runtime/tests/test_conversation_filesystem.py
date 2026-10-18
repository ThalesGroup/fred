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
from fred_runtime.conversation_filesystem import ConversationFilesystemService
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
    first = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
    same_conversation = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
    other_conversation = ConversationFilesystemService(
        storage, "conversation-b", mutation_source="agent"
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
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()

    with pytest.raises(ConversationScratchpadInvalidPathError):
        await scratchpad.write_text(path, "must not be stored")

    assert storage.files == {}


@pytest.mark.asyncio
async def test_physical_namespace_allows_safe_deep_named_subdirectory() -> None:
    storage = _MemoryFilesystem()
    namespace = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
    await namespace.write_text(".deep/internal.md", "trusted")
    assert await namespace.read_text(".deep/internal.md") == "trusted"


@pytest.mark.asyncio
async def test_scratchpad_rejects_non_text_before_storage() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()

    with pytest.raises(ConversationScratchpadUnsupportedContentError):
        await scratchpad.write_text("binary.dat", b"\xff")  # type: ignore[arg-type]

    assert storage.files == {}


@pytest.mark.parametrize("session_id", ("", ".", "..", "a/b", "a\\b", "a b"))
def test_conversation_binding_rejects_unsafe_session_identifiers(
    session_id: str,
) -> None:
    with pytest.raises(ConversationScratchpadInvalidPathError):
        ConversationFilesystemService(
            _MemoryFilesystem(), session_id, mutation_source="agent"
        )


@pytest.mark.asyncio
async def test_stale_edit_preserves_latest_content() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
    await scratchpad.write_text("notes.md", "latest content")

    with pytest.raises(ConversationScratchpadEditConflictError):
        await scratchpad.edit_text("notes.md", "earlier content", "replacement")

    assert await scratchpad.read_text("notes.md") == "latest content"


@pytest.mark.asyncio
async def test_full_write_replaces_and_edit_uses_latest_content() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
    await scratchpad.write_text("notes.md", "first draft")
    await scratchpad.write_text("notes.md", "second draft")

    match_count = await scratchpad.edit_text("notes.md", "second", "final")

    assert match_count == 1
    assert await scratchpad.read_text("notes.md") == "final draft"


@pytest.mark.asyncio
async def test_edit_requires_unique_match_unless_replace_all_is_explicit() -> None:
    storage = _MemoryFilesystem()
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
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
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()
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
        _FailingFilesystem(), "conversation-a", mutation_source="agent"
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
        mutation_source="agent",
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
        mutation_source="agent",
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
        mutation_source="agent",
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
        mutation_source="agent",
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
        mutation_source="agent",
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
        mutation_source="agent",
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
    scratchpad = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    ).scratchpad()

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
        mutation_source="agent",
    )
    first = service.scratchpad()
    second = ConversationFilesystemService(
        storage,
        "conversation-a",
        quotas=_quotas(scratchpad_max_files=1),
        mutation_source="agent",
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
        mutation_source="agent",
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
        mutation_source="agent",
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
        _FailingFilesystem(), "private-conversation", mutation_source="agent"
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
async def test_external_autosaves_publish_one_durable_full_diff() -> None:
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="agent"
    )
    user = ConversationFilesystemService(
        storage, "conversation-a", mutation_source="user"
    )
    await agent.scratchpad().write_text("report.md", "first\n")
    await user.scratchpad().write_text("report.md", "draft\n")
    await user.scratchpad().edit_text("report.md", "draft", "reviewed")

    replica_storage = _MemoryFilesystem()
    replica_storage.files = storage.files
    replica = ConversationFilesystemService(
        replica_storage, "conversation-a", mutation_source="agent"
    )
    publication = await replica.publish_external_changes("exchange-2")
    deep = replica.namespace(".deep", max_bytes=1_000_000, max_files=100)

    assert publication.file_count == 1
    assert publication.paths == ("/.deep/changes/exchange-2/report.md.diff",)
    assert await deep.list("changes/exchange-2") == (
        "changes/exchange-2/report.md.diff",
    )
    assert await deep.read_text("changes/exchange-2/report.md.diff") == (
        "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-first\n+reviewed\n"
    )


@pytest.mark.asyncio
async def test_only_successful_external_net_changes_enter_history() -> None:
    class FailingStorage(_MemoryFilesystem):
        async def write(self, path: str, data: bytes | str) -> None:
            if path.endswith("/failed.md"):
                raise OSError("unavailable")
            await super().write(path, data)

    storage = FailingStorage()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    external = ConversationFilesystemService(storage, "c")
    await agent.scratchpad().write_text("same.md", "original\n")
    await external.scratchpad().write_text("same.md", "original\n")
    await external.scratchpad().write_text("same.md", "temporary\n")
    await external.scratchpad().write_text("same.md", "original\n")
    await external.namespace(".deep", max_bytes=100000, max_files=100).write_text(
        "internal", "runtime"
    )
    with pytest.raises(ConversationScratchpadStorageError):
        await external.scratchpad().write_text("failed.md", "not saved")
    assert (await agent.publish_external_changes("turn-1")).paths == ()
    await external.scratchpad().write_text("background.md", "independent\n")
    assert (await agent.publish_external_changes("turn-2")).paths == (
        "/.deep/changes/turn-2/background.md.diff",
    )


@pytest.mark.asyncio
async def test_creation_and_deletion_publish_dev_null_headers() -> None:
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    external = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("old.md", "removed\n")
    await external.scratchpad().delete("old.md")
    await external.scratchpad().write_text("new.md", "created\n")
    await external.scratchpad().write_text("transient.md", "gone\n")
    await external.scratchpad().delete("transient.md")
    publication = await agent.publish_external_changes("turn")
    deep = agent.namespace(".deep", max_bytes=100000, max_files=100)
    assert publication.file_count == 2
    assert (
        await deep.read_text("changes/turn/old.md.diff")
        == "--- /old.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-removed\n"
    )
    assert (
        await deep.read_text("changes/turn/new.md.diff")
        == "--- /dev/null\n+++ /new.md\n@@ -0,0 +1 @@\n+created\n"
    )


@pytest.mark.asyncio
async def test_partial_save_reports_saved_content_and_recovers_history_on_retry() -> (
    None
):
    class PartialStorage(_MemoryFilesystem):
        fail = True

        async def write(self, path: str, data: bytes | str) -> None:
            if (
                path.endswith("/.changes/state.json")
                and self.fail
                and self.files.get("conversations/c/scratchpad/report.md") == b"saved\n"
            ):
                self.fail = False
                raise OSError("bookkeeping unavailable")
            await super().write(path, data)

    storage = PartialStorage()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "before\n")
    with pytest.raises(ConversationScratchpadStorageError, match="file changed"):
        await user.scratchpad().write_text("report.md", "saved\n")
    assert await agent.scratchpad().read_text("report.md") == "saved\n"
    assert (await agent.publish_external_changes("turn")).file_count == 1
    assert (
        await agent.namespace(".deep", max_bytes=100000, max_files=100).read_text(
            "changes/turn/report.md.diff"
        )
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-before\n+saved\n"
    )


@pytest.mark.asyncio
async def test_sealed_turn_does_not_block_or_consume_later_saves() -> None:
    class PausedStorage(_MemoryFilesystem):
        started = asyncio.Event()
        release = asyncio.Event()

        async def exists(self, path: str) -> bool:
            if "/changes/turn-1/" in path:
                self.started.set()
                await self.release.wait()
            return await super().exists(path)

    storage = PausedStorage()
    service = ConversationFilesystemService(storage, "c", mutation_source="user")
    await service.scratchpad().write_text("report.md", "one\n")
    publishing = asyncio.create_task(service.publish_external_changes("turn-1"))
    await storage.started.wait()
    try:
        await asyncio.wait_for(
            service.scratchpad().write_text("report.md", "two\n"), timeout=1
        )
    finally:
        storage.release.set()
        first = await publishing
    assert (await service.publish_external_changes("turn-1")) == first
    second = await service.publish_external_changes("turn-2")
    assert second.paths == ("/.deep/changes/turn-2/report.md.diff",)
    deep = service.namespace(".deep", max_bytes=100000, max_files=100)
    assert (
        await deep.read_text("changes/turn-2/report.md.diff")
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-one\n+two\n"
    )


@pytest.mark.asyncio
async def test_history_is_flat_collision_safe_and_preserves_exact_source_headers() -> (
    None
):
    service = ConversationFilesystemService(
        _MemoryFilesystem(), "c", mutation_source="user"
    )
    paths = [
        "report.md",
        "a/report.md",
        "b/report.md",
        "a%2Freport.md",
        "été.md",
        "report.md.001",
        "/".join(["x" * 180] * 4),
    ]
    for path in paths:
        await service.scratchpad().write_text(path, "new\n")
    result = await service.publish_external_changes("turn")
    deep = service.namespace(".deep", max_bytes=100000, max_files=100)
    listing = await deep.list("changes/turn")
    assert len(listing) == len(paths)
    assert "changes/turn/report.md.diff" in listing
    assert all(
        len(path.split("/")) == 3 and len(path.rsplit("/", 1)[1].encode()) <= 255
        for path in listing
    )
    headers = {(await deep.read_text(path)).splitlines()[1] for path in listing}
    assert headers == {"+++ /" + path for path in paths}
    assert result.file_count == 7


@pytest.mark.asyncio
async def test_unterminated_text_and_empty_file_creation_have_complete_diffs() -> None:
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    external = ConversationFilesystemService(storage, "c")
    await agent.scratchpad().write_text("report.md", "before")
    await external.scratchpad().write_text("report.md", "after")
    await external.scratchpad().write_text("empty.txt", "")
    await external.publish_external_changes("turn")
    deep = external.namespace(".deep", max_bytes=100000, max_files=100)
    assert (
        await deep.read_text("changes/turn/report.md.diff")
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-before\n\\ No newline at end of file\n+after\n\\ No newline at end of file\n"
    )
    assert (
        await deep.read_text("changes/turn/empty.txt.diff")
        == "--- /dev/null\n+++ /empty.txt\n"
    )


@pytest.mark.asyncio
async def test_deleting_a_directory_records_each_removed_text_file() -> None:
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("sections/one.md", "one\n")
    await agent.scratchpad().write_text("sections/two.md", "two\n")
    await user.scratchpad().delete("sections")
    assert (await user.publish_external_changes("turn")).file_count == 2


@pytest.mark.asyncio
async def test_partial_publication_is_not_acknowledged_and_retry_finishes_same_interval() -> (
    None
):
    class InterruptedPublication(_MemoryFilesystem):
        fail = True

        async def write(self, path: str, data: bytes | str) -> None:
            if path.endswith("/two.md.diff") and self.fail:
                self.fail = False
                raise OSError("publication failed")
            await super().write(path, data)

    storage = InterruptedPublication()
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await user.scratchpad().write_text("one.md", "one\n")
    await user.scratchpad().write_text("two.md", "two\n")
    with pytest.raises(ConversationScratchpadStorageError):
        await user.publish_external_changes("turn-1")
    await user.scratchpad().write_text("later.md", "later\n")
    replica = ConversationFilesystemService(storage, "c", mutation_source="agent")
    first = await replica.publish_external_changes("turn-1")
    assert first.file_count == 2
    assert set(first.paths) == {
        "/.deep/changes/turn-1/one.md.diff",
        "/.deep/changes/turn-1/two.md.diff",
    }
    assert (await replica.publish_external_changes("turn-2")).paths == (
        "/.deep/changes/turn-2/later.md.diff",
    )
    assert (
        await replica.namespace(".deep", max_bytes=100000, max_files=100).read_text(
            "changes/turn-1/one.md.diff"
        )
        == "--- /dev/null\n+++ /one.md\n@@ -0,0 +1 @@\n+one\n"
    )


@pytest.mark.asyncio
async def test_pending_history_uses_deep_quota_before_mutating_the_working_file() -> (
    None
):
    storage = _MemoryFilesystem()
    user = ConversationFilesystemService(
        storage,
        "c",
        mutation_source="user",
        quotas=_quotas(scratchpad_max_bytes=1000, deep_max_bytes=100),
    )
    with pytest.raises(ConversationScratchpadQuotaExceededError):
        await user.scratchpad().write_text("report.md", "large external edit" * 10)
    assert not await user.scratchpad().exists("report.md")


@pytest.mark.asyncio
async def test_published_history_uses_quota_retains_old_diffs_and_erases_with_namespace() -> (
    None
):
    storage = _MemoryFilesystem()
    quotas = _quotas(
        scratchpad_max_bytes=100000, deep_max_bytes=100000, deep_max_files=2
    )
    user = ConversationFilesystemService(
        storage, "c", mutation_source="user", quotas=quotas
    )
    await user.scratchpad().write_text("report.md", "one\n")
    first = await user.publish_external_changes("turn-1")
    await user.scratchpad().write_text("report.md", "two\n")
    with pytest.raises(ConversationScratchpadQuotaExceededError):
        await user.publish_external_changes("turn-2")
    deep = user.namespace(".deep", max_bytes=100000, max_files=2)
    assert (
        await deep.read_text("changes/turn-1/report.md.diff")
        == "--- /dev/null\n+++ /report.md\n@@ -0,0 +1 @@\n+one\n"
    )
    assert await user.scratchpad().read_text("report.md") == "two\n"
    assert await user.publish_external_changes("turn-1") == first
    expanded = ConversationFilesystemService(
        storage,
        "c",
        mutation_source="user",
        quotas=_quotas(deep_max_bytes=100000, deep_max_files=10),
    )
    assert (await expanded.publish_external_changes("turn-2")).file_count == 1
    await expanded.scratchpad().write_text("report.md", "pending\n")
    await user.purge_namespace("scratchpad")
    await user.purge_namespace(".deep")
    assert await user.scratchpad().list() == ()
    assert await deep.list() == ()
    assert (await expanded.publish_external_changes("turn-3")).file_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["../other/file.md", "/absolute.md", "folder/../file.md"]
)
async def test_optional_text_reads_preserve_namespace_confinement(path: str) -> None:
    service = ConversationFilesystemService(
        _MemoryFilesystem(), "c", mutation_source="agent"
    )
    with pytest.raises(ConversationScratchpadInvalidPathError):
        await service.scratchpad().read_optional_text(path)


@pytest.mark.asyncio
async def test_nonprinting_source_path_is_quoted_as_data_in_diff_headers() -> None:
    service = ConversationFilesystemService(
        _MemoryFilesystem(), "c", mutation_source="user"
    )
    await service.scratchpad().write_text('report\x7f".md', "new\n")
    publication = await service.publish_external_changes("turn")
    deep = service.namespace(".deep", max_bytes=100000, max_files=100)
    assert (
        await deep.read_text(publication.paths[0].removeprefix("/.deep/"))
    ).splitlines()[1] == '+++ "/report\\u007f\\".md"'


@pytest.mark.asyncio
async def test_source_names_resembling_generated_names_never_overwrite_other_diffs() -> (
    None
):
    service = ConversationFilesystemService(
        _MemoryFilesystem(), "c", mutation_source="user"
    )
    deep = service.namespace(".deep", max_bytes=1000000, max_files=100)
    long_path = "x" * 120 + "/" + "y" * 120
    await service.scratchpad().write_text(long_path, "first\n")
    first = await service.publish_external_changes("turn-1")
    resembling = first.paths[0].rsplit("/", 1)[1].removesuffix(".diff")
    await service.scratchpad().write_text(long_path, "second\n")
    await service.scratchpad().write_text(resembling, "second\n")
    second = await service.publish_external_changes("turn-2")
    for path in second.paths:
        diff = await deep.read_text(path.removeprefix("/.deep/"))
        if diff.splitlines()[1] == "+++ /" + resembling:
            third_name = path.rsplit("/", 1)[1].removesuffix(".diff")
            break
    else:
        pytest.fail("Second source's diff is missing")
    for path in (long_path, resembling, third_name):
        await service.scratchpad().write_text(path, "third\n")
    third = await service.publish_external_changes("turn-3")
    assert third.file_count == 3
    assert len(third.paths) == 3
    headers = {
        (await deep.read_text(path.removeprefix("/.deep/"))).splitlines()[1]
        for path in third.paths
    }
    assert headers == {"+++ /" + path for path in (long_path, resembling, third_name)}


@pytest.mark.asyncio
async def test_diff_preserves_carriage_returns_and_unicode_line_separators() -> None:
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "first\rsecond\u2028third")
    await user.scratchpad().write_text("report.md", "changed\rsecond\u2028third")
    await user.publish_external_changes("turn")
    assert (
        await user.namespace(".deep", max_bytes=100000, max_files=100).read_text(
            "changes/turn/report.md.diff"
        )
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-first\rsecond\u2028third\n\\ No newline at end of file\n+changed\rsecond\u2028third\n\\ No newline at end of file\n"
    )


@pytest.mark.asyncio
async def test_agent_write_separates_only_external_changes_in_chronological_groups() -> (
    None
):
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "A\n")
    await user.scratchpad().write_text("report.md", "B\n")
    await agent.scratchpad().write_text("report.md", "C\n")
    await user.scratchpad().write_text("report.md", "D\n")
    publication = await agent.publish_external_changes("turn")
    assert publication.file_count == 1
    assert publication.paths == (
        "/.deep/changes/turn/report.md.001.diff",
        "/.deep/changes/turn/report.md.002.diff",
    )
    deep = agent.namespace(".deep", max_bytes=1000000, max_files=100)
    assert (
        await deep.read_text("changes/turn/report.md.001.diff")
        == "--- /report.md\tExternal change group 001\n+++ /report.md\tExternal change group 001\n@@ -1 +1 @@\n-A\n+B\n"
    )
    assert (
        await deep.read_text("changes/turn/report.md.002.diff")
        == "--- /report.md\tExternal change group 002\n+++ /report.md\tExternal change group 002\n@@ -1 +1 @@\n-C\n+D\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["write", "edit", "delete"])
async def test_failed_and_noop_agent_mutations_do_not_split_external_group(
    operation: str,
) -> None:
    from fred_runtime.conversation_filesystem import current_mutation_source

    class FailedAgentStorage(_MemoryFilesystem):
        fail = False

        async def write(self, path: str, data: bytes | str) -> None:
            if (
                self.fail
                and path.endswith("/scratchpad/report.md")
                and current_mutation_source() == "agent"
            ):
                raise OSError("working write failed")
            await super().write(path, data)

        async def delete(self, path: str) -> None:
            if self.fail and path.endswith("/scratchpad/report.md"):
                raise OSError("working delete failed")
            await super().delete(path)

    storage = FailedAgentStorage()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "A\n")
    await user.scratchpad().write_text("report.md", "B\n")
    storage.fail = True
    with pytest.raises(ConversationScratchpadStorageError):
        if operation == "write":
            await agent.scratchpad().write_text("report.md", "C\n")
        elif operation == "edit":
            await agent.scratchpad().edit_text("report.md", "B", "C")
        else:
            await agent.scratchpad().delete("report.md")
    storage.fail = False
    await agent.scratchpad().write_text("report.md", "B\n")
    await agent.scratchpad().edit_text("report.md", "B", "B")
    with pytest.raises(ConversationScratchpadEditConflictError):
        await agent.scratchpad().edit_text("report.md", "not present", "replacement")
    await agent.scratchpad().write_text("unrelated.md", "Agent activity\n")
    await user.scratchpad().write_text("report.md", "D\n")
    publication = await user.publish_external_changes("turn")
    assert publication.paths == ("/.deep/changes/turn/report.md.diff",)
    assert (
        await user.namespace(".deep", max_bytes=1000000, max_files=100).read_text(
            "changes/turn/report.md.diff"
        )
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-A\n+D\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_source", ["user", "agent"])
async def test_unfinished_mutation_is_recovered_before_next_writer_overwrites_evidence(
    failed_source: str,
) -> None:
    class PartialStorage(_MemoryFilesystem):
        fail = True

        async def write(self, path: str, data: bytes | str) -> None:
            target = b"B\n" if failed_source == "user" else b"C\n"
            if (
                self.fail
                and path.endswith("/.changes/state.json")
                and self.files.get("conversations/c/scratchpad/report.md") == target
            ):
                self.fail = False
                raise OSError("recording unavailable")
            await super().write(path, data)

    storage = PartialStorage()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "A\n")
    if failed_source == "user":
        with pytest.raises(ConversationScratchpadStorageError, match="file changed"):
            await user.scratchpad().write_text("report.md", "B\n")
        await agent.scratchpad().write_text("report.md", "C\n")
    else:
        await user.scratchpad().write_text("report.md", "B\n")
        with pytest.raises(ConversationScratchpadStorageError, match="file changed"):
            await agent.scratchpad().write_text("report.md", "C\n")
    await user.scratchpad().write_text("report.md", "D\n")
    publication = await user.publish_external_changes("turn")
    assert len(publication.paths) == 2
    deep = user.namespace(".deep", max_bytes=1000000, max_files=100)
    assert (await deep.read_text("changes/turn/report.md.001.diff")).endswith(
        "-A\n+B\n"
    )
    assert (await deep.read_text("changes/turn/report.md.002.diff")).endswith(
        "-C\n+D\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["native_edit", "helper", "concat"])
async def test_agent_adapters_close_groups_without_requiring_output_read(
    writer: str,
) -> None:
    from fred_runtime.deep.concat_files import ConcatFilesMiddleware
    from fred_runtime.deep.conversation_port import DeepConversationFilesystemPort
    from fred_runtime.deep.deep_runtime import build_conversation_filesystem

    class UnreadOutputStorage(_MemoryFilesystem):
        deny_output_read = False

        async def read(self, path: str) -> bytes:
            if self.deny_output_read and path.endswith("/scratchpad/report.md"):
                raise AssertionError(
                    "An explicit replacement must not require reading the old output"
                )
            return await super().read(path)

    storage = UnreadOutputStorage()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    backend, permissions = build_conversation_filesystem(agent)
    port = DeepConversationFilesystemPort(backend, permissions)
    await agent.scratchpad().write_text("report.md", "A\n")
    await agent.scratchpad().write_text("part.md", "C\n")
    await user.scratchpad().write_text("report.md", "B\n")
    if writer == "native_edit":
        assert (await backend.aedit("/report.md", "B", "C")).error is None
    else:
        storage.deny_output_read = True
        if writer == "helper":
            await port.write_text("/report.md", "C\n", origin="system")
        else:
            await (
                ConcatFilesMiddleware(port)
                .tools[0]
                .ainvoke(
                    {
                        "paths": ["/part.md"],
                        "output_path": "/report.md",
                        "replace": True,
                    }
                )
            )
        storage.deny_output_read = False
    assert await user.scratchpad().read_text("report.md") == "C\n"
    await user.scratchpad().write_text("report.md", "D\n")
    publication = await user.publish_external_changes("turn")
    assert len(publication.paths) == 2
    deep = user.namespace(".deep", max_bytes=1000000, max_files=100)
    assert (await deep.read_text("changes/turn/report.md.001.diff")).endswith(
        "-A\n+B\n"
    )
    assert (await deep.read_text("changes/turn/report.md.002.diff")).endswith(
        "-C\n+D\n"
    )


@pytest.mark.asyncio
async def test_agent_directory_delete_closes_each_external_group_before_recreation() -> (
    None
):
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    for path in ("sections/one.md", "sections/two.md"):
        await agent.scratchpad().write_text(path, "A\n")
        await user.scratchpad().write_text(path, "B\n")
    await agent.scratchpad().delete("sections")
    for path in ("sections/one.md", "sections/two.md"):
        await user.scratchpad().write_text(path, "D\n")
    publication = await user.publish_external_changes("turn")
    assert publication.file_count == 2
    assert len(publication.paths) == 4
    deep = user.namespace(".deep", max_bytes=1000000, max_files=100)
    assert (
        await deep.read_text("changes/turn/sections%2Fone.md.002.diff")
        == "--- /dev/null\tExternal change group 002\n+++ /sections/one.md\tExternal change group 002\n@@ -0,0 +1 @@\n+D\n"
    )


@pytest.mark.asyncio
async def test_numbered_group_names_do_not_collide_with_suffix_like_source_names() -> (
    None
):
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    for path in ("report.md", "report.md.001", "report.md.001.001"):
        await agent.scratchpad().write_text(path, "A\n")
        await user.scratchpad().write_text(path, "B\n")
    for path in ("report.md", "report.md.001"):
        await agent.scratchpad().write_text(path, "C\n")
        await user.scratchpad().write_text(path, "D\n")
    first = await user.publish_external_changes("turn-1")
    assert first.file_count == 3
    assert len(first.paths) == 5
    deep = user.namespace(".deep", max_bytes=1000000, max_files=100)
    contents = [
        await deep.read_text(path.removeprefix("/.deep/")) for path in first.paths
    ]
    assert sorted(text.splitlines()[0] for text in contents) == sorted(
        [
            "--- /report.md.001.001",
            "--- /report.md.001\tExternal change group 001",
            "--- /report.md.001\tExternal change group 002",
            "--- /report.md\tExternal change group 001",
            "--- /report.md\tExternal change group 002",
        ]
    )
    await user.scratchpad().write_text("report.md", "E\n")
    assert await user.publish_external_changes("turn-1") == first
    assert [
        await deep.read_text(path.removeprefix("/.deep/")) for path in first.paths
    ] == contents
    second = await user.publish_external_changes("turn-2")
    assert second.paths == ("/.deep/changes/turn-2/report.md.diff",)
    assert (
        await deep.read_text("changes/turn-2/report.md.diff")
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-D\n+E\n"
    )


@pytest.mark.asyncio
async def test_more_than_999_segments_sort_in_numeric_order_and_retry_keeps_names() -> (
    None
):
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "agent-0\n")
    for index in range(1, 1002):
        await user.scratchpad().write_text("report.md", f"external-{index}\n")
        if index < 1001:
            await agent.scratchpad().write_text("report.md", f"agent-{index}\n")
    publication = await agent.publish_external_changes("turn")
    deep = agent.namespace(".deep", max_bytes=10000000, max_files=2000)
    listing = await deep.list("changes/turn")
    assert len(listing) == 1001
    assert listing[0] == "changes/turn/report.md.0001.diff"
    assert listing[998:] == (
        "changes/turn/report.md.0999.diff",
        "changes/turn/report.md.1000.diff",
        "changes/turn/report.md.1001.diff",
    )
    assert tuple("/.deep/" + path for path in listing) == publication.paths
    assert (await deep.read_text(listing[0])).endswith("-agent-0\n+external-1\n")
    assert (await deep.read_text(listing[999])).endswith("-agent-999\n+external-1000\n")
    assert (await deep.read_text(listing[1000])).endswith(
        "-agent-1000\n+external-1001\n"
    )
    assert await agent.publish_external_changes("turn") == publication


@pytest.mark.asyncio
async def test_net_zero_closed_group_does_not_number_the_only_remaining_diff() -> None:
    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "A\n")
    await user.scratchpad().write_text("report.md", "temporary\n")
    await user.scratchpad().write_text("report.md", "A\n")
    await agent.scratchpad().write_text("report.md", "C\n")
    await user.scratchpad().write_text("report.md", "D\n")
    publication = await agent.publish_external_changes("turn")
    assert publication.paths == ("/.deep/changes/turn/report.md.diff",)
    assert (
        await agent.namespace(".deep", max_bytes=1000000, max_files=100).read_text(
            "changes/turn/report.md.diff"
        )
        == "--- /report.md\n+++ /report.md\n@@ -1 +1 @@\n-C\n+D\n"
    )
