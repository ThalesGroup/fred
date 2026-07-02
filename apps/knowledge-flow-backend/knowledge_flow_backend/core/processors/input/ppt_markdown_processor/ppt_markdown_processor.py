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

"""Ingestion processor for legacy binary ``.ppt`` PowerPoint files.

Fred rationale:
- ``.ppt`` (legacy OLE binary) is not readable by python-pptx, so instead of
  duplicating extraction logic we convert ``.ppt`` -> ``.pptx`` once with headless
  LibreOffice and then delegate to the existing, well-tested
  ``PptxMarkdownProcessor`` (including its profile-aware vision enrichment).
- The processor is intentionally stateless: each public method converts into its
  own temporary directory and delegates. This keeps it safe under the concurrent
  ingestion workers that share a single processor instance, at the cost of a few
  extra LibreOffice runs per document (acceptable for corpus ingestion, which is
  not latency sensitive).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from knowledge_flow_backend.core.processors.input.common.legacy_office import convert_ppt_to_pptx, looks_like_ole_binary
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.pptx_markdown_processor import PptxMarkdownProcessor

logger = logging.getLogger(__name__)


class PptMarkdownProcessor(PptxMarkdownProcessor):
    description = "Converts legacy binary PPT decks to Markdown by upgrading them to PPTX (LibreOffice) and reusing the PPTX extractor."

    def check_file_validity(self, file_path: Path) -> bool:
        """Validate that the input is a non-empty legacy OLE ``.ppt`` file.

        Cheap structural check only: we do not spawn LibreOffice here, conversion
        happens lazily in the extraction methods below.
        """
        try:
            if file_path.stat().st_size <= 0:
                logger.warning("[PPT] %s is empty.", file_path)
                return False
        except OSError as exc:
            logger.error("[PPT] Cannot stat %s: %s", file_path, exc)
            return False

        if not looks_like_ole_binary(file_path):
            logger.error("[PPT] %s is not a valid legacy OLE .ppt file.", file_path)
            return False
        return True

    def extract_file_metadata(self, file_path: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="ppt2pptx_") as tmp:
            pptx_path = convert_ppt_to_pptx(file_path, Path(tmp))
            return super().extract_file_metadata(pptx_path)

    def extract_guardrail_text(self, file_path: Path) -> str | None:
        with tempfile.TemporaryDirectory(prefix="ppt2pptx_") as tmp:
            pptx_path = convert_ppt_to_pptx(file_path, Path(tmp))
            return super().extract_guardrail_text(pptx_path)

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        with tempfile.TemporaryDirectory(prefix="ppt2pptx_") as tmp:
            pptx_path = convert_ppt_to_pptx(file_path, Path(tmp))
            return super().convert_file_to_markdown(pptx_path, output_dir, document_uid)
