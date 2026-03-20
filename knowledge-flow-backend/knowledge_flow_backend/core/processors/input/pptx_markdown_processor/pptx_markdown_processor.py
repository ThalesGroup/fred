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

"""Main PPTX Markdown processor.

This processor orchestrates PPTX-specific helper modules for native slide extraction,
formatting, speaker notes, and deck-level cleanup. The split keeps the native
extraction reusable for future multimodal PPTX processing.
"""

import logging
from pathlib import Path
from typing import Any

from pptx import Presentation

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, InputConversionError
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils.pptx_deck_noise import (
    detect_repeated_noise_texts,
)
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils.pptx_native_slide_extractor import (
    extract_native_slide_content,
)
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils.pptx_slide_markdown_formatter import (
    format_slide_markdown,
)

logger = logging.getLogger(__name__)


class PptxMarkdownProcessor(BaseMarkdownProcessor):
    description = "Converts PPTX slide decks into Markdown sections, slide by slide."

    def check_file_validity(self, file_path: Path) -> bool:
        """Checks if the PPTX file is valid and can be opened."""
        try:
            Presentation(str(file_path))
            return True
        except Exception as e:
            logger.error(f"Invalid or corrupted PPTX file: {file_path} - {e}")
            return False

    def extract_file_metadata(self, file_path: Path) -> dict[str, Any]:
        """Extracts basic metadata from the PPTX file."""
        metadata: dict[str, Any] = {"document_name": file_path.name}
        try:
            presentation = Presentation(str(file_path))
            metadata["num_slides"] = len(presentation.slides)
        except Exception as e:
            logger.error(f"Error reading PPTX file: {e}")
            metadata["error"] = str(e)
        return metadata

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """Converts each slide's content into structured Markdown."""
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"

        try:
            presentation = Presentation(str(file_path))
            slide_markdowns = []

            repeated_noise_texts = detect_repeated_noise_texts(presentation.slides)

            for slide_number, slide in enumerate(presentation.slides, start=1):
                native_content = extract_native_slide_content(
                    slide,
                    slide_number,
                    repeated_noise_texts=repeated_noise_texts,
                )
                slide_md = format_slide_markdown(native_content)
                if slide_md:
                    slide_markdowns.append(slide_md)

            content = "\n\n---\n\n".join(slide_markdowns) if slide_markdowns else "*No extractable text*"
            md_path.write_text(content, encoding="utf-8")

            return {
                "doc_dir": str(output_dir),
                "md_file": str(md_path),
                "message": "PPTX slides converted to structured Markdown.",
            }

        except Exception as exc:
            logger.exception("Failed to convert PPTX to Markdown: %s", file_path)
            raise InputConversionError(f"PptxMarkdownProcessor failed for '{file_path.name}': {exc}") from exc
