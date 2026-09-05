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

"""
Local filesystem `SourceConnector` (docs/swift/rfc/INDEXED-CORPUS-RFC.md) —
the first proof-of-concept pull connector, chosen for having no external
dependency to stand up.

Why content hash, not mtime, as `revision`:
    The Sphere connector this RFC was written against diffed files by a raw
    modified-timestamp string, which is exactly the kind of signal a `touch`
    or a clock skew can lie about. A plain local filesystem has no equivalent
    of an S3 ETag or a Sphere revision id, so a content hash is the only
    signal here that is actually trustworthy about "did the bytes change".

Why `source_item_id` is the relative path, not an inode:
    An inode would survive a rename, but nothing downstream persists an
    inode/path mapping yet to make that useful, and this is deliberately the
    simplest real connector, not the most capable one. A rename is therefore
    seen as delete+add here — a stated limitation of this connector, not a
    limitation of the `SourceConnector` contract itself.

Why the cursor encodes the whole previous listing:
    A plain filesystem has no native change feed to resume from, so the
    connector must carry its own state across calls. The opaque cursor is
    the contract's sanctioned place to do that; the caller never needs to
    parse it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fred_sdk.contracts.connector import ChangeKind, SourceChange, SourceItem


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalFilesystemConnector:
    """Discovers and fetches files under one local directory, recursively."""

    def __init__(self, root_path: Path) -> None:
        if not root_path.is_dir():
            raise ValueError(f"LocalFilesystemConnector root is not a directory: {root_path}")
        self._root = root_path

    def discover_changes(self, cursor: str | None) -> tuple[list[SourceChange], str]:
        previous: dict[str, str] = json.loads(cursor) if cursor else {}
        current: dict[str, str] = {path.relative_to(self._root).as_posix(): _sha256_file(path) for path in sorted(self._root.rglob("*")) if path.is_file()}

        changes: list[SourceChange] = []
        for relative_path, revision in current.items():
            if previous.get(relative_path) == revision:
                continue
            stat = (self._root / relative_path).stat()
            changes.append(
                SourceChange(
                    item=SourceItem(
                        source_item_id=relative_path,
                        revision=revision,
                        display_path=relative_path,
                        size_bytes=stat.st_size,
                    ),
                    kind=ChangeKind.UPSERT,
                )
            )

        for relative_path, revision in previous.items():
            if relative_path in current:
                continue
            changes.append(
                SourceChange(
                    item=SourceItem(
                        source_item_id=relative_path,
                        revision=revision,
                        display_path=relative_path,
                    ),
                    kind=ChangeKind.DELETE,
                )
            )

        next_cursor = json.dumps(current, sort_keys=True)
        return changes, next_cursor

    def fetch(self, item: SourceItem, destination_dir: Path) -> Path:
        source_path = self._root / item.display_path
        destination_path = destination_dir / item.display_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        return destination_path
