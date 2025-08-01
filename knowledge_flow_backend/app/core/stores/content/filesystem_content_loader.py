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

from pathlib import Path
import hashlib
from typing import BinaryIO, List

from app.core.stores.metadata.base_catalog_store import PullFileEntry
from app.common.document_structures import DocumentMetadata
from app.common.structures import FileSystemPullSource
from app.core.stores.content.base_content_loader import BaseContentLoader


class FileSystemContentLoader(BaseContentLoader):
    def __init__(self, source: FileSystemPullSource, source_tag: str):
        super().__init__(source, source_tag)
        self.base_path = Path(source.base_path).expanduser().resolve()

    def scan(self) -> List[PullFileEntry]:
        entries: List[PullFileEntry] = []

        for path in self.base_path.rglob("*"):
            if path.is_file():
                relative = str(path.relative_to(self.base_path))
                stat = path.stat()
                entries.append(PullFileEntry(
                    path=relative,
                    size=stat.st_size,
                    modified_time=stat.st_mtime,
                    hash=hashlib.sha256(str(path).encode()).hexdigest()
                ))

        return entries

    def fetch_from_pull_entry(self, entry: PullFileEntry, destination_dir: Path) -> Path:
        """
        For local paths, we assume the file already exists locally.

        This simply resolves the file from the configured base path,
        without copying or downloading it.

        Returns the full path to the local file.
        """
        local_path = self.base_path / entry.path
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        return local_path

    def fetch_from_metadata(self, metadata: DocumentMetadata, destination_dir: Path) -> Path:
        if not metadata.source_tag or not metadata.pull_location:
            raise ValueError("Missing `source_tag` or `pull_location` in metadata.")

        entry = PullFileEntry(
            path=metadata.pull_location,
            size=0,
            modified_time=metadata.modified.timestamp() if metadata.modified else 0,
            hash="na",
        )
        return self.fetch_from_pull_entry(entry, destination_dir)

    def fetch_by_relative_path(self, relative_path: str, destination_dir: Path) -> Path:
        full_path = self.base_path / relative_path
        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"File not found: {full_path}")
        return full_path
