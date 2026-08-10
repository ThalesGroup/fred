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

import base64
import logging
import mimetypes
import threading
from pathlib import Path

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from knowledge_flow_backend.core.processors.input.common.image_describer import (
    IMAGE_DESCRIPTION_UNAVAILABLE,
    build_image_describer,
)

logger = logging.getLogger(__name__)

# Supported image extensions
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}


class ImageProcessor(BaseMarkdownProcessor):
    """
    Processor for standalone image files ingested into a document library.

    The generated markdown always contains the filename-based title so the image
    stays retrievable by name. When a vision model is configured, a vision
    description is appended so the image content itself becomes searchable —
    same behaviour as the fast-path FastLiteImageProcessor for chat attachments.
    """

    description = "Processes image files into searchable markdown, with a vision description when a vision model is configured."

    def __init__(self) -> None:
        super().__init__()
        # Same reasoning as PdfMarkdownProcessor: this instance is a shared
        # singleton (application_context.get_input_processor_instance) called from
        # concurrent Temporal activity threads, and build_image_describer builds a
        # real provider client — so build it once and reuse it.
        self._image_describer: BaseImageDescriber | None = None
        self._image_describer_lock = threading.Lock()
        self._warned_missing_vision_model = False

    def _resolve_image_describer(self) -> BaseImageDescriber | None:
        if self._image_describer is not None:
            return self._image_describer
        vision_model = get_configuration().vision_model
        if not vision_model:
            if not self._warned_missing_vision_model:
                logger.info("[PROCESSOR][IMAGE] Vision model missing; markdown keeps filename-based content only.")
                self._warned_missing_vision_model = True
            return None
        with self._image_describer_lock:
            if self._image_describer is None:
                self._image_describer = build_image_describer(vision_model)
        return self._image_describer

    @staticmethod
    def _to_data_url(file_path: Path) -> str:
        mime = mimetypes.guess_type(file_path.name)[0] or "image/png"
        encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

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
        Generate a markdown file with the image title, metadata and — when a
        vision model is configured — a vision description of the image content.
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

        describer = self._resolve_image_describer()
        if describer is not None:
            description = describer.describe(self._to_data_url(file_path)).strip()
            if description and description != IMAGE_DESCRIPTION_UNAVAILABLE:
                markdown_content += f"\n## Vision summary\n\n{description}\n"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Created markdown file for image: {file_path.name}")

        return {"doc_dir": str(output_dir), "md_file": str(md_path), "image_title": image_title}
