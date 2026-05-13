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

from abc import ABC, abstractmethod
from pathlib import Path


class BasePdfOcrExtractor(ABC):
    """
    Why:
        Provide one small abstraction for remote PDF OCR backends so the PDF
        processor can switch between local Docling OCR and API-based OCR
        without embedding provider-specific HTTP code.

    How to use:
        Construct a concrete extractor, then call `extract_pdf_markdown(...)`
        with the PDF path to receive OCR markdown.

    Example:
        `markdown = extractor.extract_pdf_markdown(Path("/tmp/report.pdf"))`
    """

    @abstractmethod
    def extract_pdf_markdown(self, file_path: Path) -> str:
        """
        Why:
            Convert one PDF into OCR markdown using a remote provider.

        How to use:
            Pass a readable local PDF path. Implementations return one markdown
            string or raise an exception if OCR fails.
        """
