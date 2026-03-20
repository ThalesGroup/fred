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
from typing import BinaryIO, Protocol


class ContentStore(Protocol):
    """Minimal contract used by services that store binary objects.

    Why this exists:
    - Backend code should only care about "store bytes" and "get a download URL".
    - The concrete backend (MinIO or local filesystem) can change without changing
      service code.

    Basic usage:
    ```python
    from fred_core.store import ContentStore
    from io import BytesIO

    def save_logo(store: ContentStore) -> str:
        store.put_object("teams/t1/logo.png", BytesIO(b"..."), content_type="image/png")
        return store.get_presigned_url("teams/t1/logo.png")
    ```
    """

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        """Store bytes at `key`.

        Use this when you want a stable object key for later reads or downloads.

        Example:
        ```python
        from io import BytesIO

        store.put_object("reports/r1.pdf", BytesIO(pdf_bytes), content_type="application/pdf")
        ```
        """

        ...

    def get_presigned_url(
        self, key: str, expires: timedelta = timedelta(hours=1)
    ) -> str:
        """Return a temporary URL to download object `key`.

        Use this to give the frontend a direct download link without exposing
        permanent credentials.

        Example:
        ```python
        url = store.get_presigned_url("reports/r1.pdf", expires=timedelta(minutes=15))
        ```
        """

        ...
