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

"""
Pre-flight PDF document analysis for adaptive backend routing.

This module performs a lightweight, read-only inspection of a PDF before
any extraction engine is selected.  The analysis runs entirely on pypdf,
which is already a dependency of PdfMarkdownProcessor, so no new library
is introduced.

Classification rules
--------------------
SCANNED
    The document has very little extractable text relative to its page count.
    Typical indicator: scanned image-only PDF.  Needs full OCR.

COMPLEX_LAYOUT
    The document has embedded text AND detectable tables or vector graphics
    (font count heuristic).  Suitable for layout-aware extraction (Docling).

TEXT_NATIVE
    The document is born-digital with a simple text flow — no heavy table
    or image content.  A fast programmatic extraction (no OCR, no layout
    model) is sufficient.

Heuristics intentionally avoid loading all pages; only the first few sample
pages are inspected so the overhead is negligible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pypdf

logger = logging.getLogger(__name__)

# --- tuneable thresholds (class constants keep them easy to override in tests) ---
_CHARS_PER_PAGE_SCANNED_THRESHOLD = 80
_SAMPLE_PAGES = 5
_FONT_COUNT_COMPLEX_THRESHOLD = 6


class PdfNature(str, Enum):
    """Broad document type inferred during pre-flight analysis."""

    TEXT_NATIVE = "text_native"
    SCANNED = "scanned"
    COMPLEX_LAYOUT = "complex_layout"


@dataclass(frozen=True)
class PdfAnalysisResult:
    """
    Lightweight summary produced by PdfDocumentAnalyzer.

    Attributes
    ----------
    nature:
        Inferred document type used for backend routing.
    avg_chars_per_page:
        Average extractable character count across sampled pages.
        A low value (< threshold) indicates a scanned document.
    unique_font_count:
        Number of distinct /Font entries seen in sampled pages.
        A high value suggests rich typography / complex layout.
    page_count:
        Total number of pages in the document.
    has_embedded_text:
        True when at least one sampled page yielded non-empty text.
    """

    nature: PdfNature
    avg_chars_per_page: float
    unique_font_count: int
    page_count: int
    has_embedded_text: bool


class PdfDocumentAnalyzer:
    """
    Performs a fast, non-destructive pre-flight inspection of a PDF file
    and classifies it into one of the PdfNature categories.

    The analysis is intentionally cheap: only up to ``_SAMPLE_PAGES`` pages
    are inspected and no rendering or model inference is performed.

    Usage::

        analyzer = PdfDocumentAnalyzer()
        result = analyzer.analyze(Path("/tmp/document.pdf"))
        if result.nature == PdfNature.SCANNED:
            # route to OCR-heavy backend
    """

    chars_per_page_scanned_threshold: int = _CHARS_PER_PAGE_SCANNED_THRESHOLD
    sample_pages: int = _SAMPLE_PAGES
    font_count_complex_threshold: int = _FONT_COUNT_COMPLEX_THRESHOLD

    def _collect_font_names(self, page: pypdf.PageObject) -> set[str]:
        """
        Extract the set of /Font resource names from one page dictionary.

        pypdf exposes page resources as a DictionaryObject; font names are the
        keys of the /Font sub-dictionary.  Returns an empty set when the page
        has no font resources or when the resource tree cannot be read.
        """
        font_names: set[str] = set()
        try:
            resources = page.get("/Resources")
            if resources is None:
                return font_names
            fonts = resources.get("/Font")
            if fonts is None:
                return font_names
            if hasattr(fonts, "keys"):
                font_names.update(str(k) for k in fonts.keys())
        except Exception as exc:
            logger.debug("[PDF][ANALYZER] Font extraction failed on page: %s", exc)
        return font_names

    def _select_sample_indices(self, page_count: int) -> list[int]:
        """
        Choose up to ``self.sample_pages`` page indices spread across the document.

        Always includes page 0; for documents longer than sample_pages, picks
        evenly-spaced indices including the last page.
        """
        if page_count <= self.sample_pages:
            return list(range(page_count))

        step = max(1, (page_count - 1) // (self.sample_pages - 1))
        indices = list(range(0, page_count, step))[: self.sample_pages]
        if (page_count - 1) not in indices:
            indices[-1] = page_count - 1
        return indices

    def _classify(
        self,
        avg_chars: float,
        unique_font_count: int,
        has_embedded_text: bool,
    ) -> PdfNature:
        """
        Apply threshold-based classification rules.

        Priority:
        1. Very low text → SCANNED (OCR needed)
        2. Rich font set → COMPLEX_LAYOUT (layout-aware model preferred)
        3. Otherwise → TEXT_NATIVE (fast programmatic extraction)
        """
        if not has_embedded_text or avg_chars < self.chars_per_page_scanned_threshold:
            return PdfNature.SCANNED
        if unique_font_count >= self.font_count_complex_threshold:
            return PdfNature.COMPLEX_LAYOUT
        return PdfNature.TEXT_NATIVE

    def analyze(self, file_path: Path) -> PdfAnalysisResult:
        """
        Run the pre-flight analysis on *file_path* and return a result.

        Raises
        ------
        ValueError
            When the file cannot be opened or has no pages.
        """
        try:
            reader = pypdf.PdfReader(str(file_path), strict=False)
        except Exception as exc:
            raise ValueError(f"[PDF][ANALYZER] Cannot open '{file_path.name}': {exc}") from exc

        page_count = len(reader.pages)
        if page_count == 0:
            raise ValueError(f"[PDF][ANALYZER] '{file_path.name}' has no pages.")

        sample_indices = self._select_sample_indices(page_count)

        total_chars = 0
        all_fonts: set[str] = set()
        has_embedded_text = False

        for idx in sample_indices:
            page = reader.pages[idx]

            try:
                text = page.extract_text() or ""
            except Exception as exc:
                logger.debug("[PDF][ANALYZER] Text extraction failed on page %d: %s", idx, exc)
                text = ""

            char_count = len(text.strip())
            total_chars += char_count
            if char_count > 0:
                has_embedded_text = True

            all_fonts.update(self._collect_font_names(page))

        avg_chars = total_chars / len(sample_indices) if sample_indices else 0.0
        unique_font_count = len(all_fonts)
        nature = self._classify(avg_chars, unique_font_count, has_embedded_text)

        logger.info(
            "[PDF][ANALYZER] '%s' — pages=%d sampled=%d avg_chars=%.1f fonts=%d nature=%s",
            file_path.name,
            page_count,
            len(sample_indices),
            avg_chars,
            unique_font_count,
            nature.value,
        )

        return PdfAnalysisResult(
            nature=nature,
            avg_chars_per_page=avg_chars,
            unique_font_count=unique_font_count,
            page_count=page_count,
            has_embedded_text=has_embedded_text,
        )
