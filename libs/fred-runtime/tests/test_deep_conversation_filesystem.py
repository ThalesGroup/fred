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
from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.conversation_backend import (
    ConversationNamespaceBackend,
    RejectingBackend,
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


@pytest.mark.asyncio
async def test_backend_round_trips_and_lists_conversation_text() -> None:
    namespace = ConversationFilesystemService(
        _MemoryFilesystem(), "conversation-a"
    ).namespace("scratchpad")
    backend = ConversationNamespaceBackend(namespace)

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
    first = ConversationNamespaceBackend(
        ConversationFilesystemService(storage, "conversation-a").namespace("scratchpad")
    )
    fresh = ConversationNamespaceBackend(
        ConversationFilesystemService(storage, "conversation-a").namespace("scratchpad")
    )
    isolated = ConversationNamespaceBackend(
        ConversationFilesystemService(storage, "conversation-b").namespace("scratchpad")
    )

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
    namespace = ConversationFilesystemService(
        _MemoryFilesystem(), "conversation-a"
    ).namespace("scratchpad")
    backend = ConversationNamespaceBackend(namespace)
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
    namespace = ConversationFilesystemService(storage, "conversation-a").namespace(
        "scratchpad"
    )
    backend = ConversationNamespaceBackend(namespace)
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
    namespace = ConversationFilesystemService(storage, "conversation-a").namespace(
        "scratchpad"
    )
    backend = ConversationNamespaceBackend(namespace)
    for index in range(40):
        await namespace.write_text(f"notes/{index:02}.md", f"needle {index:02}")

    result = await backend.agrep("needle", path="/", glob="*.md")
    paths = [match["path"] for match in result.matches or []]

    assert result.error is None
    assert paths == [f"/notes/{index:02}.md" for index in range(40)]
    assert 2 <= storage.max_in_flight <= 16


@pytest.mark.asyncio
async def test_backends_translate_storage_and_unmounted_path_failures() -> None:
    class _FailingFilesystem(_MemoryFilesystem):
        async def read(self, path: str) -> bytes:
            del path
            raise OSError("provider detail must not leak")

    storage = _FailingFilesystem()
    storage.files["conversations/conversation-a/scratchpad/notes.md"] = b"unreadable"
    namespace = ConversationFilesystemService(storage, "conversation-a").namespace(
        "scratchpad"
    )
    backend = ConversationNamespaceBackend(namespace)
    rejecting = RejectingBackend()

    failed_read = await backend.aread("/notes.md")
    rejected_read = await rejecting.aread("/outside.md")
    rejected_write = await rejecting.awrite("/outside.md", "content")
    rejected_edit = await rejecting.aedit("/outside.md", "old", "new")
    rejected_list = await rejecting.als("/")
    rejected_glob = await rejecting.aglob("**/*", path="/")
    rejected_grep = await rejecting.agrep("text", path="/")

    assert failed_read.error == "Shared scratchpad storage failed"
    assert rejected_read.error == "Path is outside mounted conversation filesystems"
    assert rejected_write.error == rejected_read.error
    assert rejected_edit.error == rejected_read.error
    assert rejected_list.error == rejected_read.error
    assert rejected_glob.error == rejected_read.error
    assert rejected_grep.error == rejected_read.error
