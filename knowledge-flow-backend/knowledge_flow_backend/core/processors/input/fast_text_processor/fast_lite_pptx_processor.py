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

from pathlib import Path

from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastPageText,
    FastTextOptions,
    FastTextResult,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    LiteMarkdownOptions,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pptx_to_md_processor import (
    LitePptxToMdExtractor,
)


class FastLitePptxProcessor(BaseFastTextProcessor):
    """Adapter to use LitePptxToMdExtractor within the FastText infrastructure."""

    def __init__(self) -> None:
        self._lite = LitePptxToMdExtractor()

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        opts = options or FastTextOptions()
        lite_opts = LiteMarkdownOptions(
            include_tables=opts.include_tables,
            max_table_rows=opts.max_table_rows,
            max_table_cols=opts.max_table_cols,
            include_images=opts.include_images,
            page_range=opts.page_range,
            max_chars=opts.max_chars,
            normalize_whitespace=opts.normalize_whitespace,
            add_page_headings=opts.add_page_headings,
            return_per_page=opts.return_per_page,
            trim_empty_lines=opts.trim_empty_lines,
        )
        result = self._lite.extract(file_path, lite_opts)

        pages = [FastPageText(page_no=p.page_no, text=p.markdown, char_count=p.char_count) for p in (result.pages or [])]

        return FastTextResult(
            document_name=result.document_name,
            page_count=result.page_count,
            total_chars=result.total_chars,
            truncated=result.truncated,
            text=result.markdown,
            pages=pages,
            extras=result.extras,
        )
