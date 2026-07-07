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

"""Unit tests for GcsFilesystem using an in-memory fake GCS client (no network)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fred_core.filesystem.structures import FilesystemResourceInfo


class _FakeBlob:
    def __init__(self, store: dict, name: str):
        self._store = store
        self.name = name

    # --- metadata (populated for blobs returned by list/get) ---
    @property
    def size(self):
        data = self._store.get(self.name)
        return None if data is None else len(data)

    @property
    def updated(self):
        return (
            datetime(2026, 1, 1, tzinfo=timezone.utc)
            if self.name in self._store
            else None
        )

    @property
    def etag(self):
        return "etag" if self.name in self._store else None

    @property
    def content_type(self):
        return "application/octet-stream"

    # --- operations ---
    def upload_from_string(self, data, content_type=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._store[self.name] = data

    def download_as_bytes(self, start=None, end=None):
        from google.cloud.exceptions import NotFound

        if self.name not in self._store:
            raise NotFound(self.name)
        data = self._store[self.name]
        if start is None and end is None:
            return data
        return data[start : (end + 1) if end is not None else None]

    def exists(self):
        return self.name in self._store

    def delete(self):
        from google.cloud.exceptions import NotFound

        if self.name not in self._store:
            raise NotFound(self.name)
        del self._store[self.name]


class _FakeBucket:
    def __init__(self, store: dict):
        self._store = store

    def blob(self, name):
        return _FakeBlob(self._store, name)

    def get_blob(self, name):
        return _FakeBlob(self._store, name) if name in self._store else None


class _FakeClient:
    def __init__(self, store: dict):
        self._store = store

    def bucket(self, name):
        return _FakeBucket(self._store)

    def list_blobs(self, bucket_name, prefix="", max_results=None):
        names = sorted(k for k in self._store if k.startswith(prefix or ""))
        if max_results is not None:
            names = names[:max_results]
        return [_FakeBlob(self._store, n) for n in names]


@pytest.fixture
def gcs_fs(monkeypatch):
    from fred_core.filesystem import gcs_filesystem

    store: dict[str, bytes] = {}
    monkeypatch.setattr(
        gcs_filesystem.storage, "Client", lambda *a, **k: _FakeClient(store)
    )
    fs = gcs_filesystem.GcsFilesystem(bucket_name="test-bucket")
    return fs


@pytest.mark.asyncio
async def test_roundtrip_listing_and_grep(gcs_fs):
    await gcs_fs.mkdir("docs")
    await gcs_fs.mkdir("docs/nested")
    await gcs_fs.write("docs/readme.txt", "hello world")
    await gcs_fs.write("docs/nested/notes.txt", "fred runtime notes")

    assert await gcs_fs.print_root_dir() == "gs://test-bucket"
    assert await gcs_fs.exists("docs/readme.txt") is True
    assert await gcs_fs.read("docs/readme.txt") == b"hello world"
    assert await gcs_fs.cat("docs/nested/notes.txt") == "fred runtime notes"

    info = await gcs_fs.stat("docs/readme.txt")
    assert info.path == "docs/readme.txt"
    assert info.type == FilesystemResourceInfo.FILE
    assert info.size == len("hello world")

    listing = await gcs_fs.list("docs")
    # Like the MinIO backend, directories are inferred from key prefixes, so the
    # queried prefix and its sub-prefixes appear alongside the files.
    by_path = {e.path: e for e in listing}
    assert by_path["docs"].type == FilesystemResourceInfo.DIRECTORY
    assert by_path["docs/nested"].type == FilesystemResourceInfo.DIRECTORY
    assert by_path["docs/readme.txt"].type == FilesystemResourceInfo.FILE
    assert by_path["docs/nested/notes.txt"].type == FilesystemResourceInfo.FILE
    assert by_path["docs/readme.txt"].size == len("hello world")
    assert [e.path for e in listing] == sorted(e.path for e in listing)

    matches = await gcs_fs.grep(r"fred\s+runtime", "docs")
    assert matches == ["docs/nested/notes.txt"]


@pytest.mark.asyncio
async def test_write_requires_existing_parent(gcs_fs):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        await gcs_fs.write("missing/readme.txt", "hello")


@pytest.mark.asyncio
async def test_read_missing_raises(gcs_fs):
    with pytest.raises(FileNotFoundError, match="Object not found"):
        await gcs_fs.read("nope.txt")


@pytest.mark.asyncio
async def test_stat_missing_is_virtual_directory(gcs_fs):
    info = await gcs_fs.stat("ghost")
    assert info.type == FilesystemResourceInfo.DIRECTORY
    assert info.size is None


@pytest.mark.asyncio
async def test_delete_recurses_then_listing_is_empty(gcs_fs):
    await gcs_fs.mkdir("docs")
    await gcs_fs.write("docs/a.txt", "a")
    await gcs_fs.write("docs/b.txt", "b")

    await gcs_fs.delete("docs")

    assert await gcs_fs.exists("docs/a.txt") is False
    assert await gcs_fs.list("docs") == []


@pytest.mark.asyncio
async def test_prefix_isolates_logical_root(monkeypatch):
    from fred_core.filesystem import gcs_filesystem

    store: dict[str, bytes] = {}
    monkeypatch.setattr(
        gcs_filesystem.storage, "Client", lambda *a, **k: _FakeClient(store)
    )
    fs = gcs_filesystem.GcsFilesystem(bucket_name="b", prefix="vfs")

    await fs.mkdir("docs")
    await fs.write("docs/x.txt", "data")

    # The configured prefix is applied transparently to the underlying key.
    assert "vfs/docs/x.txt" in store
    assert await fs.read("docs/x.txt") == b"data"
    assert await fs.print_root_dir() == "gs://b/vfs"


@pytest.mark.asyncio
async def test_list_does_not_leak_sibling_prefix(monkeypatch):
    """A configured root must not match siblings sharing its string prefix.

    With prefix="team-a", listing the logical root must not return objects from
    "team-alpha/...", since GCS prefixes are raw string matches (see the
    slash-boundary in GcsFilesystem.list).
    """
    from fred_core.filesystem import gcs_filesystem

    # Two logical roots share one bucket; their prefixes share a string prefix.
    store: dict[str, bytes] = {
        "team-a/docs/own.txt": b"mine",
        "team-alpha/docs/secret.txt": b"not yours",
    }
    monkeypatch.setattr(
        gcs_filesystem.storage, "Client", lambda *a, **k: _FakeClient(store)
    )
    fs = gcs_filesystem.GcsFilesystem(bucket_name="b", prefix="team-a")

    paths = {e.path for e in await fs.list("")}
    assert "team-a/docs/own.txt" in paths
    assert all(not p.startswith("team-alpha") for p in paths)

    # grep iterates list(), so the leak must not surface through content search.
    assert await fs.grep(r"not yours", "") == []
