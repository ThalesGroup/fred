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

from knowledge_flow_backend.core.processors.input.email_processor.email_message_parser import parse_email_file, render_email_markdown
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastTextOptions,
    FastTextResult,
    collapse_whitespace,
    enforce_max_chars,
    trim_empty_lines,
)


class FastEmailProcessor(BaseFastTextProcessor):
    """Chat attachment extractor for `.msg` and `.eml`, same layout as the library path."""

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        opts = options or FastTextOptions()
        # The cap doubles as the body budget so attachment extraction stops once it is spent.
        text = render_email_markdown(parse_email_file(file_path), max_body_chars=opts.max_chars)
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
            extras={"file_type": "email", "extension": file_path.suffix.lower()},
        )
