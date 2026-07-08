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

from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import BinaryIO, cast

import pytest
from fred_core.store.local_content_store import LocalContentStore


def test_local_content_store_put_object_writes_bytes_and_creates_directories(
    tmp_path: Path,
) -> None:
    store = LocalContentStore(root_path=tmp_path)

    store.put_object(
        "teams/team-1/banner.png",
        BytesIO(b"image-bytes"),
        content_type="image/png",
    )

    target = tmp_path / "objects" / "teams" / "team-1" / "banner.png"
    assert target.read_bytes() == b"image-bytes"


def test_local_content_store_accepts_text_stream_payload(tmp_path: Path) -> None:
    store = LocalContentStore(root_path=tmp_path)

    store.put_object(
        "teams/team-1/readme.txt",
        cast(BinaryIO, StringIO("hello fred")),
        content_type="text/plain",
    )

    target = tmp_path / "objects" / "teams" / "team-1" / "readme.txt"
    assert target.read_text() == "hello fred"


def test_local_content_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = LocalContentStore(root_path=tmp_path)

    with pytest.raises(ValueError, match="escapes storage root"):
        store.put_object(
            "../escape.txt",
            BytesIO(b"bad"),
            content_type="text/plain",
        )


def test_local_content_store_presigned_url_is_not_supported(
    tmp_path: Path,
) -> None:
    store = LocalContentStore(root_path=tmp_path)

    with pytest.raises(NotImplementedError, match="Presigned URLs are not supported"):
        store.get_presigned_url("teams/team-1/banner.png", expires=timedelta(minutes=5))
