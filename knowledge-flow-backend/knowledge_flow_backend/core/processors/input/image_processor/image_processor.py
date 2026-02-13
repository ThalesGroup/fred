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

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor

logger = logging.getLogger(__name__)

# Supported image extensions
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}


class ImageProcessor(BaseMarkdownProcessor):
    """
    Processor for image files that stores image metadata and generates a markdown file
    with the image title/name for searching and indexing.

    The image filename (without extension) is used as the searchable title/keyword.
    For example: "Apple.png" -> title="Apple", "Nvidia.jpg" -> title="Nvidia"
    """

    description = "Processes image files and extracts metadata for searchable indexing."

    def check_file_validity(self, file_path: Path) -> bool:
        """Check if the file is a valid image format."""
        if not file_path.exists():
            logger.warning(f"Image file does not exist: {file_path}")
            return False

        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            logger.warning(f"Unsupported image format: {file_path.suffix}")
            return False

        # Basic file size check (not empty)
        if file_path.stat().st_size == 0:
            logger.warning(f"Image file is empty: {file_path}")
            return False

        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Extract metadata from the image file.
        The filename (without extension) serves as the searchable title.
        """
        # Use the filename without extension as the title/keyword
        image_title = file_path.stem

        metadata = {
            "document_name": file_path.name,
            "title": image_title,  # This will be searchable
            "file_size_bytes": file_path.stat().st_size,
            "file_type": "image",
            "extras": {
                "image.format": file_path.suffix.lower().lstrip("."),
                "image.searchable_name": image_title,
            },
        }

        logger.info(f"Extracted metadata for image: {file_path.name} with title '{image_title}'")
        return metadata

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Generate a minimal markdown file containing the image title and metadata.
        This allows the image to be searchable by its filename.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"
        image_title = file_path.stem

        # Create markdown content with the title as searchable text
        markdown_content = f"""# {image_title}

**Type**: Image Logo/Icon
**Format**: {file_path.suffix.lower().lstrip(".")}
**Filename**: {file_path.name}

This is an image asset that can be used in templates. Search for "{image_title}" to find this image.
"""

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Created markdown file for image: {file_path.name}")

        return {"doc_dir": str(output_dir), "md_file": str(md_path), "image_title": image_title}
