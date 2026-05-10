from __future__ import annotations

from pathlib import Path

import pytest

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
