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
from abc import ABC, abstractmethod
from pathlib import Path
from app.common.document_structures import DocumentMetadata
from app.common.source_utils import resolve_source_type
import pandas

logger = logging.getLogger(__name__)


class BaseInputProcessor(ABC):
    """
    Base class for all processors that handle file metadata extraction and processing.
    This class provides a common interface and utility methods for file processing.
    """

    def _generate_file_unique_id(self, document_name: str) -> str:
        """
        Generate a unique identifier for the file based on its metadata.
        This identifier is used to track the file in the system.
        """
        return hashlib.sha256(document_name.encode("utf-8")).hexdigest()

    def _add_common_metadata(self, file_path: Path, tags: list[str], source_tag: str) -> DocumentMetadata:
        document_uid = self._generate_file_unique_id(file_path.name)
        source_type = resolve_source_type(source_tag)
        return DocumentMetadata(document_name=file_path.name, document_uid=document_uid, tags=tags, source_tag=source_tag, source_type=source_type)

    def process_metadata(self, file_path: Path, tags: list[str], source_tag: str = "uploads") -> DocumentMetadata:
        if not self.check_file_validity(file_path):
            return {"document_name": file_path.name, "error": "Invalid file structure"}

        # Step 1: Create initial metadata
        base_metadata = self._add_common_metadata(file_path, tags, source_tag)

        # Step 2: Extract enrichment fields (e.g., author, created, etc.)
        enrichment = self.extract_file_metadata(file_path)

        # Step 3: Merge fields into base model
        enriched_dict = base_metadata.model_dump()
        enriched_dict.update(enrichment)

        # Step 4: Return final validated model
        return DocumentMetadata(**enriched_dict)

    def check_file_validity(self, file_path: Path) -> bool:
        pass

    @abstractmethod
    def extract_file_metadata(self, file_path: Path) -> dict:
        pass


class BaseMarkdownProcessor(BaseInputProcessor):
    """For processors that convert to Markdown."""

    @abstractmethod
    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Convert the input file to a Markdown format and save it in the output directory.
        Args:
            file_path (Path): The path to the input file.
            output_dir (Path): The directory where the converted file will be saved.
            document_uid (str): The unique identifier for the document.
        Returns:
            dict: A dictionary containing the paths to the converted files.
        """
        pass


class BaseTabularProcessor(BaseInputProcessor):
    """For processors that convert to structured tabular format (e.g., SQL rows)."""

    @abstractmethod
    def convert_file_to_table(self, file_path: Path) -> pandas.DataFrame:
        pass
