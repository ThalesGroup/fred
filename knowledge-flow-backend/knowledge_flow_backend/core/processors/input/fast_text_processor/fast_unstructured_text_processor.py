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
from collections import defaultdict
from pathlib import Path

from unstructured.partition.auto import partition

from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastPageText,
    FastTextOptions,
    FastTextResult,
    collapse_whitespace,
    enforce_max_chars,
    trim_empty_lines,
)

logger = logging.getLogger(__name__)


class FastUnstructuredTextProcessingProcessor(BaseFastTextProcessor):
    """
    Facade to select the right fast text extractor based on file suffix.
    Currently, a placeholder for future implementations.
    """

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        logger.info(f"Extracting {file_path} to text")
        opts = options or FastTextOptions()
        try:
            elements = partition(filename=str(file_path))
            page_map: dict[int, list[str]] = defaultdict(list)

            for el in elements:
                category = getattr(el, "category", None)
                if not opts.include_tables and category == "Table":
                    continue
                if not opts.include_images and category in {"Image", "Figure"}:
                    continue
                meta = getattr(el, "metadata", None)
                page_no = getattr(meta, "page_number", None) or 1
                if opts.page_range and not (opts.page_range[0] <= page_no <= opts.page_range[1]):
                    continue
                page_map[page_no].append(str(el))

            def normalize_text(text: str) -> str:
                if opts.normalize_whitespace:
                    text = collapse_whitespace(text)
                if opts.trim_empty_lines:
                    text = trim_empty_lines(text)
                return text

            page_texts: list[tuple[int, str]] = []
            for page_no in sorted(page_map.keys()):
                page_text = "\n\n".join(page_map[page_no])
                page_text = normalize_text(page_text)
                if page_text.strip():
                    page_texts.append((page_no, page_text))

            content_parts: list[str] = []
            for page_no, page_text in page_texts:
                if opts.add_page_headings:
                    content_parts.append(f"## Page {page_no}")
                content_parts.append(page_text)
            content = normalize_text("\n\n".join(content_parts)) if content_parts else ""

            content, truncated = enforce_max_chars(content, opts.max_chars)
            pages = [FastPageText(page_no=page_no, text=page_text, char_count=len(page_text)) for page_no, page_text in page_texts] if opts.return_per_page else []
            page_count = len(page_texts) if page_texts else None
            return FastTextResult(
                document_name=file_path.name,
                page_count=page_count,
                total_chars=len(content),
                truncated=truncated,
                text=content,
                pages=pages,
            )
        except Exception:
            logger.exception("Failed to extract %s to text", file_path)
            raise
