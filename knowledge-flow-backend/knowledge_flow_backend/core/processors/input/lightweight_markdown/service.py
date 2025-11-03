from __future__ import annotations

from pathlib import Path

from .docx_lite import DocxLiteMarkdownExtractor
from .lite_types import LiteMarkdownOptions, LiteMarkdownResult
from .pdf_lite import PdfLiteMarkdownExtractor


class LightweightMarkdownService:
    """Facade to select the right lightweight extractor based on file suffix."""

    def __init__(self) -> None:
        self._pdf = PdfLiteMarkdownExtractor()
        self._docx = DocxLiteMarkdownExtractor()

    def extract(self, file_path: Path, options: LiteMarkdownOptions | None = None) -> LiteMarkdownResult:
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            return self._pdf.extract(file_path, options)
        if ext == ".docx":
            return self._docx.extract(file_path, options)
        raise ValueError(f"Unsupported file type for lightweight markdown: {ext}")
