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
import pandas

from knowledge_flow_app.common.utils import utc_now_iso

logger = logging.getLogger(__name__)


class BaseInputProcessor(ABC):
    """
    Base class for all processors that handle file metadata extraction and processing.
    This class provides a common interface and utility methods for file processing.
    """

    def _generate_file_unique_id(self, metadata: dict, front_metadata: dict) -> str:
        """
        Generate a unique identifier for the file based on its metadata.
        This identifier is used to track the file in the system.
        """
        document_name = metadata.get("document_name", "")
        # Combine both fields into a deterministic string
        identifier_str = f"{document_name}"
        return hashlib.sha256(identifier_str.encode("utf-8")).hexdigest()

    def _add_common_metadata(self, file_path: Path, front_metadata: dict) -> dict:
        common_metadata = {
            "document_name": file_path.name,
            "date_added_to_kb": utc_now_iso(),
            "retrievable": True,
        }
        common_metadata["document_uid"] = self._generate_file_unique_id(common_metadata, front_metadata)
        return common_metadata

    def _sanitize_front_metadata(self, front_metadata: dict) -> dict:
        sanitized = {key.replace(" ", "_"): (value if value else "unknown") for key, value in front_metadata.items() if value not in (None, "", [], {})}
        return sanitized

    def validate_metadata(self, metadata: dict) -> None:
        required_fields = ["document_uid"]
        for field in required_fields:
            if field not in metadata:
                raise ValueError(f"Missing required metadata field: {field}")

    def process_metadata(self, file_path: Path, front_metadata: dict = None) -> dict:
        """
        Process the metadata of the input file.
        This method is responsible for extracting metadata from the file and
        validating it. It also generates a unique identifier for the file.

        Args:
            file_path (Path): The path to the input file.
        Returns:
            dict: A dictionary containing the processed metadata.
        Raises:
            ValueError: If the metadata is invalid or if required fields are missing.
        """
        if not self.check_file_validity(file_path):
            return {"document_name": file_path.name, "error": "Invalid file structure"}
        final_metadata = {}
        file_metadata = self.extract_file_metadata(file_path)
        common_metadata = self._add_common_metadata(file_path, front_metadata)

        if front_metadata:
            final_metadata["front_metadata"] = self._sanitize_front_metadata(front_metadata)

        final_metadata.update(file_metadata)
        final_metadata.update(common_metadata)

        self.validate_metadata(final_metadata)
        return final_metadata

    @abstractmethod
    def check_file_validity(self, file_path: Path) -> bool:
        pass

    @abstractmethod
    def extract_file_metadata(self, file_path: Path) -> dict:
        pass


class BaseMarkdownProcessor(BaseInputProcessor):
    """For processors that convert to Markdown."""

    @abstractmethod
    def convert_file_to_markdown(self, file_path: Path, output_dir: Path) -> dict:
        """
        Convert the input file to a Markdown format and save it in the output directory.
        Args:
            file_path (Path): The path to the input file.
            output_dir (Path): The directory where the converted file will be saved.
        Returns:
            dict: A dictionary containing the paths to the converted files.
        """
        pass


class BaseTabularProcessor(BaseInputProcessor):
    """For processors that convert to structured tabular format (e.g., SQL rows)."""

    @abstractmethod
    def convert_file_to_table(self, file_path: Path) -> pandas.DataFrame:
        pass
