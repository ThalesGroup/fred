# Copyright Thales 2026
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
    FastTextOptions,
    FastTextResult,
    collapse_whitespace,
    enforce_max_chars,
    trim_empty_lines,
)


class FastPlainTextProcessor(BaseFastTextProcessor):
    """Fast extractor for plain text and markdown attachments."""

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        opts = options or FastTextOptions()
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if opts.normalize_whitespace:
            text = collapse_whitespace(text)
        if opts.trim_empty_lines:
            text = trim_empty_lines(text)
        text, truncated = enforce_max_chars(text, opts.max_chars)
        return FastTextResult(
            document_name=file_path.name,
            page_count=1,
            total_chars=len(text),
            truncated=truncated,
            text=text,
            extras={"file_type": "text", "extension": file_path.suffix.lower()},
        )
