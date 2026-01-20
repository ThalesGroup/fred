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
            content = "\n\n".join([str(el) for el in elements])
            if opts.normalize_whitespace:
                content = collapse_whitespace(content)
            if opts.trim_empty_lines:
                content = trim_empty_lines(content)
            content, truncated = enforce_max_chars(content, opts.max_chars)
            # TODO: Create pages for big documents
            pages = [FastPageText(page_no=1, text=content, char_count=len(content))] if opts.return_per_page else []
            return FastTextResult(
                document_name=file_path.name,
                page_count=1,
                total_chars=len(content),
                truncated=truncated,
                text=content,
                pages=pages,
            )
        except Exception as e:
            logger.error(f"Failed to extract {file_path} to text: {e}")
            raise e
