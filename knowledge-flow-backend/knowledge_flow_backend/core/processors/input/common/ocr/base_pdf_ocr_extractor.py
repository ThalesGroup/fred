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
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RemotePdfOcrImage:
    """
    Why:
        Carry one image emitted by a remote OCR provider so Fred can reuse the
        existing vision enrichment path on top of API-generated OCR markdown.

    How to use:
        Providers populate the stable image identifier used in markdown plus the
        raw base64 payload. Callers match `image_id` against markdown image
        references and send `image_base64` to a vision model when needed.

    Example:
        `image = RemotePdfOcrImage(image_id="img-1.jpeg", image_base64="iVBOR...")`
    """

    image_id: str
    image_base64: str


@dataclass(slots=True)
class RemotePdfOcrPage:
    """
    Why:
        Preserve per-page remote OCR output so Fred can keep markdown ordering
        while still accessing any page-scoped image payloads.

    How to use:
        Providers create one instance per OCR page with the page markdown and
        optional image list. Callers then aggregate pages into a document-level
        result.

    Example:
        `page = RemotePdfOcrPage(markdown="# Page 1", images=[image])`
    """

    markdown: str
    images: list[RemotePdfOcrImage] = field(default_factory=list)


@dataclass(slots=True)
class RemotePdfOcrResult:
    """
    Why:
        Expose both markdown and extracted images from remote OCR in one small,
        provider-agnostic container.

    How to use:
        Providers return this from `extract_pdf_result(...)`. Call
        `to_markdown()` for the concatenated markdown, or inspect `pages` to
        enrich image references with a vision model.

    Example:
        `markdown = result.to_markdown()`
    """

    pages: list[RemotePdfOcrPage] = field(default_factory=list)

    def to_markdown(self) -> str:
        """
        Why:
            Give callers the same document-level markdown view regardless of
            whether they need per-page image data.

        How to use:
            Call after OCR extraction. The method concatenates non-empty page
            markdown blocks with blank lines and returns the final string.
        """
        return "\n\n".join(page.markdown.strip() for page in self.pages if page.markdown.strip()).strip()


class BasePdfOcrExtractor(ABC):
    """
    Why:
        Provide one small abstraction for remote PDF OCR backends so the PDF
        processor can switch between local Docling OCR and API-based OCR
        without embedding provider-specific HTTP code.

    How to use:
        Construct a concrete extractor, then call `extract_pdf_result(...)`
        when you need structured OCR output or `extract_pdf_markdown(...)`
        when the plain markdown string is enough.

    Example:
        `markdown = extractor.extract_pdf_markdown(Path("/tmp/report.pdf"))`
    """

    @abstractmethod
    def extract_pdf_result(self, file_path: Path, *, include_images: bool = False) -> RemotePdfOcrResult:
        """
        Why:
            Convert one PDF into structured OCR output using a remote provider.

        How to use:
            Pass a readable local PDF path. Implementations return one markdown
            result or raise an exception if OCR fails.

        Example:
            `result = extractor.extract_pdf_result(Path("/tmp/report.pdf"), include_images=True)`
        """

    def extract_pdf_markdown(self, file_path: Path) -> str:
        """
        Why:
            Keep a plain-markdown convenience entrypoint for callers that do
            not need per-image OCR payloads.

        How to use:
            Pass a readable local PDF path. The default implementation delegates
            to `extract_pdf_result(...)` and returns the concatenated markdown.

        Example:
            `markdown = extractor.extract_pdf_markdown(Path("/tmp/report.pdf"))`
        """
        return self.extract_pdf_result(file_path).to_markdown()
