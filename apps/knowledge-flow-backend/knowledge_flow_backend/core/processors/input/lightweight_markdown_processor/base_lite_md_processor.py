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

from abc import ABC, abstractmethod
from pathlib import Path

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownOptions, LiteMarkdownResult


class BaseLiteMdProcessor(ABC):
    """
    Base interface for all lightweight file-to-Markdown processors. These
    processors convert various file types into Markdown format with minimal
    dependencies and resource usage.

    A typical usage is to generate a Markdown representation of a file's
    content to be attached to a conversation or document in Fred, without
    the overhead of full parsing or indexing.

    All subclasses must implement the 'extract' method, which takes
    a file path and options, and returns a LiteMarkdownResult.
    """

    @abstractmethod
    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        """
        Extracts content from a file and returns it as a LiteMarkdownResult.

        :param file_path: The Path object pointing to the file.
        :param options: Configuration options for extraction (e.g., max chars/rows).
        :return: A LiteMarkdownResult containing the Markdown string and metadata.
        """
        pass
