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

"""Lightweight legacy ``.ppt`` -> Markdown extractor for chat attachments.

Fred rationale:
- Mirrors :class:`LitePptxToMdExtractor`, but for the legacy binary ``.ppt``
  format which python-pptx cannot read directly.
- Converts ``.ppt`` -> ``.pptx`` once with headless LibreOffice and then reuses
  the existing lite PPTX extractor, so attachment behaviour stays identical
  (slide-wise extraction, normalization, truncation) regardless of source format.
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
from pathlib import Path

from knowledge_flow_backend.core.processors.input.common.legacy_office import convert_ppt_to_pptx
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.base_lite_md_processor import BaseLiteMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownOptions, LiteMarkdownResult
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pptx_to_md_processor import LitePptxToMdExtractor

logger = logging.getLogger(__name__)


class LitePptToMdExtractor(BaseLiteMdProcessor):
    """Fast legacy PPT-to-Markdown converter: LibreOffice upgrade + lite PPTX extractor."""

    description = "Fast legacy PPT-to-Markdown converter using LibreOffice (PPT->PPTX) and the lite PPTX extractor."

    def __init__(self) -> None:
        self._pptx = LitePptxToMdExtractor()

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        opts = options or LiteMarkdownOptions()
        with tempfile.TemporaryDirectory(prefix="ppt2pptx_") as tmp:
            pptx_path = convert_ppt_to_pptx(file_path, Path(tmp))
            result = self._pptx.extract(pptx_path, opts)

        # Preserve the original .ppt identity and record the source format.
        extras = {**(result.extras or {}), "source_format": "ppt"}
        return dataclasses.replace(result, document_name=file_path.name, extras=extras)
