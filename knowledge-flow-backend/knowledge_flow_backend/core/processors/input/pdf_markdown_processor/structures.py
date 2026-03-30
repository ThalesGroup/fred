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

from dataclasses import dataclass
from enum import Enum


class PdfComplexity(str, Enum):
    """Supported PDF families used by the document-aware routing logic."""

    DIGITALLY_BORN_TEXT_PDF = "digitally_born_text_pdf"
    SCANNED_PDF = "scanned_pdf"
    SCIENTIFIC_PDF = "scientific_pdf"
    TABLE_HEAVY = "table_heavy"
    SLIDE_LIKE = "slide_like"
    MULTICOLUMN = "multicolumn"


@dataclass(frozen=True)
class PdfComplexityStats:
    """
    Why:
        Keep PDF routing decisions explicit and testable before the expensive
        conversion step starts.

    How:
        Populate this structure from a lightweight PDF inspection pass, then feed
        it into `PdfMarkdownProcessor._classify_pdf_kind()`.
    """

    page_count: int
    total_text_chars: int
    pages_without_text: int
    pages_with_images: int

    @property
    def average_text_chars_per_page(self) -> float:
        """
        Why:
            Expose a stable density signal for distinguishing simple digital PDFs
            from scanned or layout-heavy documents.

        How:
            Read the computed average after constructing the stats instance.
        """
        if self.page_count <= 0:
            return 0.0
        return self.total_text_chars / self.page_count

    @property
    def textless_page_ratio(self) -> float:
        """
        Why:
            Many scanned or image-heavy PDFs have little extractable text on a
            large share of pages.

        How:
            Read the computed ratio after constructing the stats instance.
        """
        if self.page_count <= 0:
            return 1.0
        return self.pages_without_text / self.page_count

    @property
    def image_page_ratio(self) -> float:
        """
        Why:
            Different document families show very different image densities, which
            helps with early routing before full parsing.

        How:
            Read the computed ratio after constructing the stats instance.
        """
        if self.page_count <= 0:
            return 0.0
        return self.pages_with_images / self.page_count
