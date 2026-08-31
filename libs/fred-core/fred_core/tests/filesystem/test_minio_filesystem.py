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

from unittest.mock import MagicMock

import pytest

from fred_core.filesystem.minio_filesystem import MinioFilesystem


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
