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

"""Behavioural coverage for Deep's conversation-backed scratchpad."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from deepagents.middleware.filesystem import FilesystemPermission
from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.conversation_backend import (
    ConversationNamespaceBackend,
)
from fred_runtime.deep.conversation_port import DeepConversationFilesystemPort
from fred_runtime.deep.deep_runtime import build_conversation_filesystem
from fred_sdk.contracts.runtime import (
    ConversationFilesystemInterruptError,
    ConversationFilesystemPermissionError,
    ConversationScratchpadInvalidPathError,
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
        self.files[path] = data if isinstance(data, bytes) else data.encode()

    async def list(self, prefix: str = "") -> list[FilesystemResourceInfoResult]:
        return [
            FilesystemResourceInfoResult(
                path=path,
                size=len(content),
                type=FilesystemResourceInfo.FILE,
                modified=datetime.now(UTC),
            )
            for path, content in sorted(self.files.items())
            if path.startswith(prefix)
        ]

    async def delete(self, path: str) -> None:
        self.files.pop(path, None)

    async def mkdir(self, path: str) -> None:
        del path

    async def exists(self, path: str) -> bool:
        return path in self.files


class _ConcurrentReadFilesystem(_MemoryFilesystem):
    def __init__(self) -> None:
        super().__init__()
        self.in_flight = 0
        self.max_in_flight = 0
        self._overlap = asyncio.Event()

    async def read(self, path: str) -> bytes:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if self.in_flight >= 2:
            self._overlap.set()
        try:
            await asyncio.wait_for(self._overlap.wait(), timeout=1)
            return await super().read(path)
        finally:
            self.in_flight -= 1


class _ReadCountingFilesystem(_MemoryFilesystem):
    def __init__(self) -> None:
        super().__init__()
        self.read_count = 0

    async def read(self, path: str) -> bytes:
        self.read_count += 1
        return await super().read(path)


def _backend(service: ConversationFilesystemService) -> ConversationNamespaceBackend:
    return ConversationNamespaceBackend(
        service,
        namespace_id="scratchpad",
        max_bytes=100 * 1024 * 1024,
        max_files=1000,
    )


@pytest.mark.asyncio
async def test_backend_round_trips_and_lists_conversation_text() -> None:
    backend = _backend(
        ConversationFilesystemService(_MemoryFilesystem(), "conversation-a")
    )

    write = await backend.awrite("/research/notes.md", "first\nsecond")
    read = await backend.aread("/research/notes.md", offset=1, limit=1)
    listing = await backend.als("/research")

    assert write.error is None
    assert write.path == "/research/notes.md"
    assert read.error is None
    assert read.file_data == {"content": "second", "encoding": "utf-8"}
    assert listing.error is None
    assert listing.entries == [
        {"path": "/research/notes.md", "is_dir": False, "size": 12}
    ]


@pytest.mark.asyncio
async def test_fresh_backends_share_one_conversation_and_isolate_another() -> None:
    storage = _MemoryFilesystem()
    first = _backend(ConversationFilesystemService(storage, "conversation-a"))
    fresh = _backend(ConversationFilesystemService(storage, "conversation-a"))
    isolated = _backend(ConversationFilesystemService(storage, "conversation-b"))

    assert (await first.awrite("/notes.md", "durable")).error is None

    assert (await fresh.aread("/notes.md")).file_data == {
        "content": "durable",
        "encoding": "utf-8",
    }
    assert (await isolated.aread("/notes.md")).error == (
        "Scratchpad file does not exist"
    )


@pytest.mark.asyncio
async def test_backend_edits_globs_and_greps_with_deep_results() -> None:
    service = ConversationFilesystemService(_MemoryFilesystem(), "conversation-a")
    namespace = service.scratchpad()
    backend = _backend(service)
    await namespace.write_text("research/one.md", "needle and needle")
    await namespace.write_text("research/two.txt", "needle elsewhere")

    conflict = await backend.aedit(
        "/research/one.md", "needle", "found", replace_all=False
    )
    edited = await backend.aedit(
        "/research/one.md", "needle", "found", replace_all=True
    )
    globbed = await backend.aglob("**/*.md", path="/")
    grepped = await backend.agrep("found", path="/", glob="*.md")

    assert conflict.path is None
    assert conflict.occurrences is None
    assert conflict.error == (
        "Expected text does not uniquely match the latest scratchpad content"
    )
    assert edited.error is None
    assert edited.path == "/research/one.md"
    assert edited.occurrences == 2
    assert globbed.error is None
    assert globbed.matches == [
        {"path": "/research/one.md", "is_dir": False, "size": 15}
    ]
    assert grepped.error is None
    assert grepped.matches == [
        {"path": "/research/one.md", "line": 1, "text": "found and found"}
    ]


@pytest.mark.asyncio
async def test_backend_lists_and_globs_from_storage_metadata_without_reads() -> None:
    storage = _ReadCountingFilesystem()
    service = ConversationFilesystemService(storage, "conversation-a")
    namespace = service.scratchpad()
    backend = _backend(service)
    await namespace.write_text("research/notes.md", "café")
    await namespace.write_text("research/raw.txt", "ignored")

    listing = await backend.als("/research")
    globbed = await backend.aglob("**/*.md", path="/")

    assert listing.entries == [
        {"path": "/research/notes.md", "is_dir": False, "size": 5},
        {"path": "/research/raw.txt", "is_dir": False, "size": 7},
    ]
    assert globbed.matches == [
        {"path": "/research/notes.md", "is_dir": False, "size": 5}
    ]
    assert storage.read_count == 0


@pytest.mark.asyncio
async def test_backend_grep_bounds_parallel_reads() -> None:
    storage = _ConcurrentReadFilesystem()
    service = ConversationFilesystemService(storage, "conversation-a")
    namespace = service.scratchpad()
    backend = _backend(service)
    for index in range(40):
        await namespace.write_text(f"notes/{index:02}.md", f"needle {index:02}")

    result = await backend.agrep("needle", path="/", glob="*.md")
    paths = [match["path"] for match in result.matches or []]

    assert result.error is None
    assert paths == [f"/notes/{index:02}.md" for index in range(40)]
    assert 2 <= storage.max_in_flight <= 16


@pytest.mark.asyncio
async def test_backend_translates_storage_failures() -> None:
    class _FailingFilesystem(_MemoryFilesystem):
        async def read(self, path: str) -> bytes:
            del path
            raise OSError("provider detail must not leak")

    storage = _FailingFilesystem()
    storage.files["conversations/conversation-a/scratchpad/notes.md"] = b"unreadable"
    backend = _backend(ConversationFilesystemService(storage, "conversation-a"))
    failed_read = await backend.aread("/notes.md")

    assert failed_read.error == "Shared scratchpad storage failed"


@pytest.mark.asyncio
async def test_virtual_port_and_backend_share_mounts_and_exact_text() -> None:
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(storage, "conversation-a")
    backend, permissions = build_conversation_filesystem(service)
    port = DeepConversationFilesystemPort(backend, permissions)
    content = "first\r\nsecond\rthird  \n" + "x" * 20000

    assert (await backend.awrite("/notes.txt", content)).error is None
    assert await port.read_text("/notes.txt", origin="agent") == content
    await port.write_text("/joined.txt", content, origin="agent")
    assert (await backend.adownload_files(["/joined.txt"]))[
        0
    ].content == content.encode()

    await port.write_text("/.deep/artifact.txt", "internal", origin="system")
    assert await port.read_text("/.deep/artifact.txt", origin="agent") == "internal"
    assert await port.list("/", origin="agent") == (
        "/.deep/artifact.txt",
        "/joined.txt",
        "/notes.txt",
    )
    with pytest.raises(ConversationFilesystemPermissionError):
        await port.write_text("/.deep/blocked.txt", "no", origin="agent")
    with pytest.raises(ConversationFilesystemPermissionError):
        await port.write_text("/.deep", "shadow", origin="agent")
    assert (
        "conversations/conversation-a/scratchpad/.deep/blocked.txt" not in storage.files
    )
    assert "conversations/conversation-a/.deep/blocked.txt" not in storage.files


@pytest.mark.asyncio
async def test_virtual_port_rule_order_interrupt_and_invalid_path() -> None:
    service = ConversationFilesystemService(_MemoryFilesystem(), "conversation-a")
    backend, _ = build_conversation_filesystem(service)
    port = DeepConversationFilesystemPort(
        backend,
        [
            FilesystemPermission(
                operations=["write"], paths=["/allowed/**"], mode="allow"
            ),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
        ],
    )
    await port.write_text("/allowed/file.txt", "yes", origin="agent")
    with pytest.raises(ConversationFilesystemPermissionError):
        await port.write_text("/blocked.txt", "no", origin="agent")

    interrupted = DeepConversationFilesystemPort(
        backend,
        [FilesystemPermission(operations=["read"], paths=["/**"], mode="interrupt")],
    )
    with pytest.raises(ConversationFilesystemInterruptError):
        await interrupted.read_text("/allowed/file.txt", origin="agent")
    assert await interrupted.read_text("/allowed/file.txt", origin="system") == "yes"
    with pytest.raises(ConversationScratchpadInvalidPathError):
        await port.read_text("/allowed/../file.txt", origin="system")


@pytest.mark.asyncio
async def test_backend_download_overwrite_and_quota_preserve_existing_file() -> None:
    class _SmallQuotas:
        scratchpad_max_bytes = 5
        scratchpad_max_files = 1
        deep_max_bytes = 5
        deep_max_files = 1

    service = ConversationFilesystemService(
        _MemoryFilesystem(), "conversation-a", quotas=_SmallQuotas()
    )
    backend, permissions = build_conversation_filesystem(service)
    port = DeepConversationFilesystemPort(backend, permissions)
    assert (await backend.awrite("/note.txt", "first")).error is None
    assert (await backend.awrite("/note.txt", "short")).error is None
    assert (await backend.awrite("/note.txt", "too long")).error is not None
    downloads = await backend.adownload_files(["/note.txt", "/missing.txt"])
    assert downloads[0].content == b"short"
    assert downloads[1].error == "file_not_found"
    assert await port.exists("/note.txt", origin="agent")
    assert not await port.exists("/missing.txt", origin="agent")
