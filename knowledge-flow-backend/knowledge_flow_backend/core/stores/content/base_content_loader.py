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


from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, List

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.common.structures import DocumentSourceConfig
from knowledge_flow_backend.core.stores.catalog.base_catalog_store import PullFileEntry


class BaseContentLoader(ABC):
    def __init__(self, source: DocumentSourceConfig, source_tag: str):
        self.source = source
        self.source_tag = source_tag

    def get_file_stream(self, relative_path: str) -> BinaryIO:
        """
        Return a binary stream for the given file path.
        Must be overridden by loaders that support streaming.
        Default: fetch to temp file and open.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = self.fetch_by_relative_path(relative_path, Path(tmpdir))
            return open(tmp_path, "rb")

    def fetch_by_relative_path(self, relative_path: str, destination_dir: Path) -> Path:
        raise NotImplementedError("This loader does not support direct fetch by relative path.")

    @abstractmethod
    def scan(self) -> List[PullFileEntry]:
        """List remote files from a pull source."""
        pass

    @abstractmethod
    def fetch_from_pull_entry(self, entry: PullFileEntry, destination_dir: Path) -> Path:
        """
        Fetch a file (or folder) from the remote source and store it locally.

        Returns the path to the downloaded file or folder.
        """
        pass

    @abstractmethod
    def fetch_from_metadata(self, metadata: DocumentMetadata, destination_dir: Path) -> Path:
        """
        Fetch a file based on metadata and store it locally.

        Returns the path to the downloaded file.
        """
        pass
