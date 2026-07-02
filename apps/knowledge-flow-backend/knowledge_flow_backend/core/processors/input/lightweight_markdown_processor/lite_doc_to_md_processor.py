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

"""Lightweight legacy ``.doc`` -> Markdown extractor for chat attachments.

Fred rationale:
- Mirrors :class:`LiteDocxToMdProcessor`, but for the legacy binary ``.doc``
  format which markitdown/python-docx cannot read directly.
- Converts ``.doc`` -> ``.docx`` once with headless LibreOffice and then reuses
  the existing lite DOCX extractor, so attachment behaviour stays identical
  (normalization, truncation, per-page API) regardless of the source format.
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
from pathlib import Path

from knowledge_flow_backend.core.processors.input.common.legacy_office import convert_doc_to_docx
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_docx_to_md_processor import LiteDocxToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownOptions, LiteMarkdownResult

logger = logging.getLogger(__name__)


class LiteDocToMdProcessor(BaseLiteMdProcessor):
    """Fast legacy DOC-to-Markdown converter: LibreOffice upgrade + lite DOCX extractor."""

    description = "Fast legacy DOC-to-Markdown converter using LibreOffice (DOC->DOCX) and the lite DOCX extractor."

    def __init__(self) -> None:
        self._docx = LiteDocxToMdProcessor()

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()
        with tempfile.TemporaryDirectory(prefix="doc2docx_") as tmp:
            docx_path = convert_doc_to_docx(file_path, Path(tmp))
            result = self._docx.extract(docx_path, opts)

        # Preserve the original .doc identity and record the source format.
        extras = {**(result.extras or {}), "source_format": "doc"}
        return dataclasses.replace(result, document_name=file_path.name, extras=extras)
