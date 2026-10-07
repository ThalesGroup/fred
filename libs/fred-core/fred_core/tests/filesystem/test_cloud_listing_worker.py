# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Cloud listing must preserve its result without doing conversion on the loop."""

import threading
from types import SimpleNamespace

import pytest
from fred_core.filesystem import gcs_filesystem, minio_filesystem
from fred_core.filesystem.structures import FilesystemResourceInfo


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [minio_filesystem, gcs_filesystem])
async def test_cloud_listing_converts_in_worker_and_preserves_collisions(
    module, monkeypatch
):
    cls = module.MinioFilesystem if module is minio_filesystem else module.GcsFilesystem
    fs = object.__new__(cls)
    fs.bucket_name, fs.prefix, fs.base_prefix = "synthetic", None, ""
    keys = ["docs/a", "docs/a/", "docs/a/file", "docs/empty/", "docs/a/other"]
    objects = [
        SimpleNamespace(
            object_name=key, name=key, size=3, last_modified=None, updated=None
        )
        for key in keys
    ]
    threads = []

    def listing(*args, **kwargs):
        assert kwargs["prefix"] == "docs/"
        threads.append(threading.get_ident())
        return objects

    fs.client = SimpleNamespace(list_objects=listing, list_blobs=listing)
    original = module.FilesystemResourceInfoResult

    def convert(**kwargs):
        threads.append(threading.get_ident())
        return original(**kwargs)

    monkeypatch.setattr(module, "FilesystemResourceInfoResult", convert)
    result = await fs.list("docs")
    assert threads and threading.get_ident() not in threads
    assert len(set(threads)) == 1
    assert [r.path for r in result] == sorted(r.path for r in result)
    # Preserve the current backends' differing treatment of an empty GCS marker.
    expected_dirs = {"docs", "docs/a"}
    if module is minio_filesystem:
        expected_dirs.add("docs/empty")
    assert {r.path for r in result if r.is_dir()} == expected_dirs
    files = [r for r in result if r.type == FilesystemResourceInfo.FILE]
    assert [r.path for r in files] == ["docs/a", "docs/a/file", "docs/a/other"]
    assert all(r.size == 3 for r in files)
    assert len(result) == len(expected_dirs) + 3  # file/directory collision survives
