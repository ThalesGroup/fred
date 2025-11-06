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

from __future__ import annotations

import logging
from pathlib import Path

from .csv_lite import CsvLiteMarkdownExtractor
from .docx_lite import DocxLiteMarkdownExtractor
from .lite_types import LiteMarkdownOptions, LiteMarkdownResult
from .pdf_lite import PdfLiteMarkdownExtractor

logger = logging.getLogger(__name__)


class LightweightMarkdownError(Exception):
    """Erreur métier pour l'extraction Markdown légère."""


class UnsupportedLightweightType(LightweightMarkdownError):
    pass


class LightweightExtractionFailed(LightweightMarkdownError):
    pass


class LightweightMarkdownService:
    """Facade to select the right lightweight extractor based on file suffix.

    Raises dedicated business exceptions for clearer error handling at controller level.
    """

    def __init__(self) -> None:
        self._pdf = PdfLiteMarkdownExtractor()
        self._docx = DocxLiteMarkdownExtractor()
        self._csv = CsvLiteMarkdownExtractor()

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        ext = (file_path.suffix or "").lower()
        try:
            if ext == ".pdf":
                return self._pdf.extract(file_path, options)
            if ext == ".docx":
                return self._docx.extract(file_path, options)
            if ext == ".csv":
                return self._csv.extract(file_path, options)
        except Exception as e:
            logger.warning(f"Lightweight extraction failed for {file_path.name}: {e}")
            raise LightweightExtractionFailed(f"Failed to extract lightweight Markdown from '{file_path.name}': {e}")

        raise UnsupportedLightweightType(f"Unsupported file type for lightweight extraction: '{ext}' (only .pdf, .docx, .csv are supported)")
