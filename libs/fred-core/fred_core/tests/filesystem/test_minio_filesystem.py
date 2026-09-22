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

"""MinioFilesystem.read must release the connection back to the pool.

Regression: read() called get_object().read() then only close() — never
release_conn() — so every read leaked a urllib3 connection. A multi-file zip
download exhausted the pool and later reads failed with a generic download error.
"""

import asyncio
import logging
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fred_core.filesystem.minio_filesystem import MinioFilesystem
from minio.error import S3Error


def _fs_with_response(response: MagicMock) -> MinioFilesystem:
    # Bypass __init__ (it connects to a live MinIO); wire only what read() touches.
    fs = MinioFilesystem.__new__(MinioFilesystem)
    fs.bucket_name = "bucket"
    fs.prefix = None
    fs.client = MagicMock()
    fs.client.get_object.return_value = response
    return fs


@pytest.mark.asyncio
async def test_read_releases_connection():
    resp = MagicMock()
    resp.read.return_value = b"hello"
    fs = _fs_with_response(resp)

    data = await fs.read("notes.txt")

    assert data == b"hello"
    resp.close.assert_called_once()
    resp.release_conn.assert_called_once()


@pytest.mark.asyncio
async def test_read_releases_connection_even_on_error():
    resp = MagicMock()
    resp.read.side_effect = RuntimeError("boom")
    fs = _fs_with_response(resp)

    with pytest.raises(RuntimeError):
        await fs.read("notes.txt")

    # The finally clause must run so the connection is never leaked on failure.
    resp.close.assert_called_once()
    resp.release_conn.assert_called_once()


@pytest.mark.asyncio
async def test_read_translates_missing_object_to_file_not_found():
    fs = _fs_with_response(MagicMock())
    fs.client.get_object.side_effect = S3Error(
        MagicMock(),
        code="NoSuchKey",
        message="The specified key does not exist",
        resource="notes.txt",
        request_id="request-id",
        host_id="host-id",
    )

    with pytest.raises(FileNotFoundError, match="notes.txt"):
        await fs.read("notes.txt")


@pytest.mark.asyncio
async def test_read_does_not_block_the_event_loop():
    resp = MagicMock()

    def _slow_read():
        time.sleep(0.05)
        return b"hello"

    resp.read.side_effect = _slow_read
    fs = _fs_with_response(resp)
    loop = asyncio.get_running_loop()
    heartbeat = loop.create_future()
    loop.call_soon(heartbeat.set_result, None)

    assert await fs.read("notes.txt") == b"hello"
    assert heartbeat.done()


@pytest.mark.asyncio
async def test_read_info_log_does_not_expose_object_key(caplog):
    resp = MagicMock()
    resp.read.return_value = b"private"
    fs = _fs_with_response(resp)

    with caplog.at_level(logging.INFO):
        await fs.read("conversations/session/private.txt")

    assert "conversations/session/private.txt" not in caplog.text
    assert "[MINIO_READ] bucket=bucket" in caplog.text


@pytest.mark.asyncio
async def test_delete_rejects_bucket_root():
    fs = MinioFilesystem.__new__(MinioFilesystem)
    fs.bucket_name = "bucket"
    fs.prefix = None
    fs.client = MagicMock()

    with pytest.raises(ValueError, match="filesystem root"):
        await fs.delete("")

    fs.client.remove_object.assert_not_called()


@pytest.mark.asyncio
async def test_delete_propagates_recursive_object_failure():
    fs = MinioFilesystem.__new__(MinioFilesystem)
    fs.bucket_name = "bucket"
    fs.prefix = None
    fs.client = MagicMock()
    fs.client.list_objects.return_value = [
        SimpleNamespace(object_name="conversation/note.txt")
    ]
    fs.client.remove_objects.return_value = iter(
        [SimpleNamespace(object_name="conversation/note.txt")]
    )

    with pytest.raises(RuntimeError, match="Failed to delete MinIO objects"):
        await fs.delete("conversation")
