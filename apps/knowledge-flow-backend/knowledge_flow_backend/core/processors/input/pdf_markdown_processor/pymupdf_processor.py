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

import re
from pathlib import Path
from typing import List

# AGPL-3.0/Artifex-dual-licensed, optional (LICENSE-01). This module is only ever
# imported lazily, once `pdf_markdown_processor._build_extractor` has confirmed the
# 'pymupdf' extra is installed — see docs/swift/COPYLEFT-DEPENDENCIES.md.
import pymupdf4llm  # pyright: ignore[reportMissingImports]

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    collapse_whitespace,
    normalize_repeated_chars,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.base_pdf_extractor import BasePdfExtractor
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.image_transcription import ImageTranscription


class PyMuPdfExtractor(BasePdfExtractor):
    def extract(self, file_path: Path, work_dir: str) -> tuple[str, List[ImageTranscription]]:
        """Extract Markdown using pymupdf4llm with page-wise extraction and normalization."""
        pages = pymupdf4llm.to_markdown(
            file_path,
            write_images=True,
            image_path=work_dir,
            header=False,
            footer=False,
            page_chunks=True,
        )

        cleaned_pages = []
        for p in pages:
            if isinstance(p, dict):
                text = (p.get("text") or p.get("md") or "").strip()
            elif isinstance(p, str):
                text = p.strip()
            else:
                text = ""

            md_text = normalize_repeated_chars(text)
            md_text = collapse_whitespace(md_text)
            cleaned_pages.append(md_text)

        md_text = "\n".join(cleaned_pages)
        return self._extract_images_path(md_text)

    def _extract_images_path(self, md_text: str) -> tuple[str, List[ImageTranscription]]:
        """Strip pymupdf4llm image markers from Markdown and collect remaining image paths."""
        image_pattern_with_description = re.compile(
            r"!\[\]\((?P<path>[^)]+)\)\s*"
            r"\*\*-+ Start of picture text -+\*\*<br>\s*"
            r"(?P<pictext>.*?)"
            r"\s*\*\*-+ End of picture text -+\*\*<br>",
            re.DOTALL,
        )

        def _repl(m: re.Match) -> str:
            path = m.group("path")
            pictext = m.group("pictext")
            if pictext:
                return pictext.replace("<br>", "\n").strip()
            return f"![]({path})"

        md_text = image_pattern_with_description.sub(_repl, md_text)

        image_pattern = re.compile(r"!\[\]\(([^)]+)\)")
        image_paths = image_pattern.findall(md_text)

        images_transcription = [ImageTranscription(image_path=Path(p)) for p in image_paths]
        return md_text, images_transcription
