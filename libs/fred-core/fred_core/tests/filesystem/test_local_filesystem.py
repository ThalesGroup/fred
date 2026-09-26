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

import threading
from pathlib import Path

import pytest
from fred_core.filesystem import local_filesystem as local_filesystem_module
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.filesystem.structures import FilesystemResourceInfo


@pytest.mark.asyncio
async def test_local_filesystem_roundtrip_listing_and_grep(tmp_path: Path) -> None:
    filesystem = LocalFilesystem(str(tmp_path))

    await filesystem.mkdir("docs")
    await filesystem.mkdir("docs/nested")
    await filesystem.write("docs/readme.txt", "hello world")
    await filesystem.write("docs/nested/notes.txt", "fred runtime notes")

    assert await filesystem.print_root_dir() == str(tmp_path.resolve())
    assert await filesystem.exists("docs/readme.txt") is True
    assert await filesystem.read("docs/readme.txt") == b"hello world"
    assert await filesystem.cat("docs/nested/notes.txt") == "fred runtime notes"

    info = await filesystem.stat("docs/readme.txt")
    assert info.path == "docs/readme.txt"
    assert info.type == FilesystemResourceInfo.FILE
    assert info.size == len("hello world")

    listing = await filesystem.list("docs")
    assert [entry.path for entry in listing] == [
        "docs/nested",
        "docs/nested/notes.txt",
        "docs/readme.txt",
    ]
    assert listing[0].type == FilesystemResourceInfo.DIRECTORY
    assert listing[1].type == FilesystemResourceInfo.FILE

    matches = await filesystem.grep(r"fred\s+runtime", "docs")
    assert matches == ["docs/nested/notes.txt"]


@pytest.mark.asyncio
async def test_local_filesystem_rejects_missing_parent_missing_file_and_escape(
    tmp_path: Path,
) -> None:
    filesystem = LocalFilesystem(str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Parent directory does not exist"):
        await filesystem.write("missing/readme.txt", "hello")

    with pytest.raises(FileNotFoundError, match="missing.txt not found"):
        await filesystem.stat("missing.txt")

    with pytest.raises(PermissionError, match="Access outside of filesystem root"):
        await filesystem.read("../escape.txt")


@pytest.mark.asyncio
async def test_local_filesystem_delete_and_empty_list_are_safe(
    tmp_path: Path,
) -> None:
    filesystem = LocalFilesystem(str(tmp_path))

    await filesystem.mkdir("docs")
    await filesystem.write("docs/readme.txt", "hello")
    await filesystem.delete("docs/readme.txt")
    await filesystem.delete("docs/missing.txt")

    assert await filesystem.exists("docs/readme.txt") is False
    assert await filesystem.list("unknown") == []


@pytest.mark.asyncio
async def test_local_filesystem_delete_recurses_without_deleting_root(
    tmp_path: Path,
) -> None:
    filesystem = LocalFilesystem(str(tmp_path))
    await filesystem.mkdir("conversation/nested")
    await filesystem.write("conversation/nested/note.txt", "hello")

    await filesystem.delete("conversation")

    assert await filesystem.exists("conversation") is False
    with pytest.raises(ValueError, match="filesystem root"):
        await filesystem.delete("")


@pytest.mark.asyncio
async def test_local_filesystem_delete_propagates_recursive_deletion_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem = LocalFilesystem(str(tmp_path))
    await filesystem.mkdir("conversation")

    def _fail_delete(path: Path, *, ignore_errors: bool = False) -> None:
        del path
        if not ignore_errors:
            raise OSError("disk unavailable")

    monkeypatch.setattr(local_filesystem_module.shutil, "rmtree", _fail_delete)

    with pytest.raises(OSError, match="disk unavailable"):
        await filesystem.delete("conversation")


@pytest.mark.asyncio
async def test_local_filesystem_rejects_sibling_with_shared_root_prefix(
    tmp_path: Path,
) -> None:
    filesystem = LocalFilesystem(str(tmp_path))
    sibling = tmp_path.parent / f"{tmp_path.name}-sibling"

    with pytest.raises(PermissionError, match="outside of filesystem root"):
        await filesystem.mkdir(f"../{sibling.name}")

    assert sibling.exists() is False


@pytest.mark.asyncio
async def test_local_filesystem_path_io_runs_outside_event_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem = LocalFilesystem(str(tmp_path))
    event_loop_thread = threading.get_ident()

    def _guard(method):
        def _wrapped(*args, **kwargs):
            assert threading.get_ident() != event_loop_thread
            return method(*args, **kwargs)

        return _wrapped

    for method_name in (
        "resolve",
        "exists",
        "mkdir",
        "is_dir",
        "rglob",
        "stat",
        "is_file",
        "unlink",
    ):
        monkeypatch.setattr(
            Path,
            method_name,
            _guard(getattr(Path, method_name)),
        )
    monkeypatch.setattr(
        local_filesystem_module.shutil,
        "rmtree",
        _guard(local_filesystem_module.shutil.rmtree),
    )

    await filesystem.mkdir("docs")
    await filesystem.write("docs/readme.txt", "hello")
    assert await filesystem.exists("docs/readme.txt") is True
    assert (await filesystem.stat("docs/readme.txt")).size == 5
    assert [entry.path for entry in await filesystem.list("docs")] == [
        "docs/readme.txt"
    ]
    await filesystem.delete("docs")
