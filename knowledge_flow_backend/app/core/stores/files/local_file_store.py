# Copyright Thales 2025
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


import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from app.core.stores.files.base_file_store import BaseFileStore, FileInfo


logger = logging.getLogger(__name__)


class LocalFileStore(BaseFileStore):
    """
    Minimal local filesystem store for PoC usage.
    Bytes in, bytes out. Stores objects under {destination_root}/{namespace}/{key}.
    """

    def __init__(self, destination_root: Path):
        self.destination_root = Path(destination_root).absolute()
        self.destination_root.mkdir(parents=True, exist_ok=True)

    def put(self, namespace: str, key: str, content: bytes, content_type: str = "application/octet-stream") -> FileInfo:
        path = self._abs_path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            f.write(content)

        sha256 = hashlib.sha256(content).hexdigest()
        guessed_type, _ = mimetypes.guess_type(str(path))
        ctype = content_type or guessed_type or "application/octet-stream"

        logger.info(f"💾 Stored '{path}' locally.")

        return FileInfo(
            uri=f"file://{path}",
            size_bytes=len(content),
            content_type=ctype,
            checksum_sha256=sha256,
        )

    def get(self, namespace: str, key: str) -> bytes:
        path = self._abs_path(namespace, key)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Object not found: {path}")
        return path.read_bytes()

    def _abs_path(self, namespace: str, key: str) -> Path:
        ns = namespace.strip("/")
        k = key.lstrip("/")
        return self.destination_root / ns / k

    def list(self, namespace: str, prefix: str = "") -> list[str]:
        base = self.destination_root / namespace.strip("/")
        root = (base / prefix.lstrip("/")) if prefix else base
        if not root.exists():
            return []
        items = []
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                full = Path(dirpath) / name
                rel = full.relative_to(base)
                items.append(str(rel).replace("\\", "/"))
        return items
