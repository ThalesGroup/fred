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

import logging
from pathlib import Path
from abc import ABC, abstractmethod
from typing import BinaryIO

logger = logging.getLogger(__name__)


class BaseContentStore(ABC):
    @abstractmethod
    def save_input(self, document_uid: str, input_dir: Path) -> None:
        """Saves the input/ folder (raw user-uploaded file)."""
        pass

    @abstractmethod
    def save_output(self, document_uid: str, output_dir: Path) -> None:
        """Saves the output/ folder (processed markdown or CSV)."""
        pass

    @abstractmethod
    def save_content(self, document_uid: str, document_dir: Path) -> None:
        """
        Uploads the content of a directory (recursively) to storage.
        The directory should contain all files related to the document.
        The document_id is used to create a unique path in the storage.
        The directory structure will be preserved in the storage.
        """
        pass

    @abstractmethod
    def delete_content(self, document_uid: str) -> None:
        """
        Deletes the content of a document from storage.
        The document_uid is used to identify the document in storage.
        """
        pass

    @abstractmethod
    def get_content(self, document_uid: str) -> BinaryIO:
        """
        Retrieve a readable binary stream for the document's primary content.

        Returns:
            BinaryIO: A file-like object you can stream from.

        Raises:
            FileNotFoundError: If the document is not found.
        """
        pass

    @abstractmethod
    def get_markdown(self, document_uid: str) -> str:
        """
        Returns the markdown content (from output/output.md).
        """
        pass

    @abstractmethod
    def get_media(self, document_uid: str, media_id: str) -> BinaryIO:
        """
        Returns the media file associated with a document.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Optional: Clear the store. Only supported by test-friendly stores.

        Default implementation does nothing and logs a debug message.
        """
        logger.debug("clear() called on BaseContentStore: no-op by default.")

    @abstractmethod
    def get_local_copy(self, document_uid: str, destination_dir: Path) -> Path:
        """
        Ensures the original uploaded file is accessible on the local filesystem.

        This is useful for workflows or processing logic that requires a real path on disk.

        Returns:
            Path: Path to the local file (guaranteed to exist).

        Raises:
            FileNotFoundError: If the content does not exist or cannot be retrieved.
        """
        pass
