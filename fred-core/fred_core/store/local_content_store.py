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
from pathlib import Path
from typing import BinaryIO


class LocalContentStore:
    """Content store backed by local disk.

    Why this exists:
    - Standalone mode can run without MinIO.
    - Files are written under one controlled root directory.

    Basic usage:
    ```python
    from io import BytesIO
    from fred_core.store import LocalContentStore

    store = LocalContentStore(root_path="./.fred-data")
    store.put_object("teams/t1/banner.png", BytesIO(b"..."), content_type="image/png")
    ```
    """

    def __init__(
        self,
        *,
        root_path: str | Path,
        object_subdir: str = "objects",
    ) -> None:
        """Create the storage directory if it does not exist.

        `root_path/object_subdir` is the only place where files will be written.
        """

        self.object_root = Path(root_path).expanduser().resolve() / object_subdir
        self.object_root.mkdir(parents=True, exist_ok=True)

    def _safe_under_root(self, key: str) -> Path:
        """Resolve an object key to a safe absolute path under storage root.

        Why this exists:
        - Reject path traversal like `../../etc/passwd`.
        - Guarantee writes stay inside the configured storage folder.
        """

        rel = Path(key.lstrip("/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Object key escapes storage root")
        path = (self.object_root / rel).resolve()
        if not path.is_relative_to(self.object_root):
            raise ValueError("Object key escapes storage root")
        return path

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        """Write object bytes to local disk at `key`.

        `content_type` is accepted for API compatibility with MinIO store.

        Example:
        ```python
        with open("banner.png", "rb") as f:
            store.put_object("teams/t1/banner.png", f, content_type="image/png")
        ```
        """

        _ = content_type
        path = self._safe_under_root(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = stream.read()
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        path.write_bytes(payload)

    def get_presigned_url(
        self, key: str, expires: timedelta = timedelta(hours=1)
    ) -> str:
        """Local store does not provide HTTP URLs.

        Why this raises:
        - Disk files are not exposed by default through a web server.
        - Returning fake URLs would hide a deployment issue.
        """

        _ = (key, expires)
        raise NotImplementedError(
            "Presigned URLs are not supported by local filesystem storage. Use MinIO storage backend instead."
        )
