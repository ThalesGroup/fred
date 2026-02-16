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
from typing import Any, Dict

from unstructured.partition.auto import partition

from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastPageText,
    FastTextOptions,
    FastTextResult,
    collapse_whitespace,
    trim_empty_lines,
)

logger = logging.getLogger(__name__)


class FastUnstructuredTextProcessingProcessor(BaseFastTextProcessor):
    """
    Facade to select the right fast text extractor based on file suffix.
    Currently, a placeholder for future implementations.
    """

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        logger.info(f"[PROCESSOR][UNSTRUCTURED] extracting {file_path} to text")
        opts = options or FastTextOptions()
        partition_kwargs: Dict[str, Any] = {"filename": str(file_path)}
        if opts.fast:
            partition_kwargs["strategy"] = "fast"
            partition_kwargs["skip_infer_table_types"] = ["pdf", "jpg", "png", "xls", "xlsx"]
        try:
            elements = partition(**partition_kwargs)
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

            max_chars = opts.max_chars if opts.max_chars and opts.max_chars > 0 else None
            content_parts: list[str] = []
            pages: list[FastPageText] = []
            included_pages: list[int] = []
            current_len = 0
            truncated = False

            def add_fragment(fragment: str) -> None:
                nonlocal current_len
                if content_parts:
                    current_len += 2
                content_parts.append(fragment)
                current_len += len(fragment)

            def remove_last_fragment() -> None:
                nonlocal current_len
                if not content_parts:
                    return
                fragment = content_parts.pop()
                remove_len = len(fragment)
                if content_parts:
                    remove_len += 2
                current_len -= remove_len

            def remaining_capacity() -> int | None:
                if max_chars is None:
                    return None
                sep = 2 if content_parts else 0
                return max_chars - current_len - sep

            for page_no, page_text in page_texts:
                if opts.add_page_headings:
                    heading = f"## Page {page_no}"
                    remaining = remaining_capacity()
                    if remaining is not None and remaining <= 0:
                        truncated = True
                        break
                    if remaining is not None and len(heading) > remaining:
                        truncated = True
                        break
                    add_fragment(heading)
                    remaining = remaining_capacity()
                    if remaining is not None and remaining <= 0:
                        remove_last_fragment()
                        truncated = True
                        break

                remaining = remaining_capacity()
                if remaining is not None:
                    if remaining <= 0:
                        truncated = True
                        break
                    if len(page_text) > remaining:
                        page_text = page_text[:remaining]
                        truncated = True

                add_fragment(page_text)
                if page_text.strip():
                    included_pages.append(page_no)
                    if opts.return_per_page:
                        pages.append(
                            FastPageText(
                                page_no=page_no,
                                text=page_text,
                                char_count=len(page_text),
                            )
                        )

                if max_chars is not None and current_len >= max_chars:
                    truncated = True
                    break

            content = normalize_text("\n\n".join(content_parts)) if content_parts else ""
            if truncated and content:
                content = content.rstrip() + "\n…"
            page_count = len(included_pages) if included_pages else None
            return FastTextResult(
                document_name=file_path.name,
                page_count=page_count,
                total_chars=len(content),
                truncated=truncated,
                text=content,
                pages=pages,
            )
        except Exception:
            logger.exception("[PROCESSOR][UNSTRUCTURED]Failed to extract %s to text", file_path)
            raise
