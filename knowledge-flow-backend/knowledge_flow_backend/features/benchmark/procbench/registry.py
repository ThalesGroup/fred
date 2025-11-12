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


from typing import Dict, List

from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import (
    DocxMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_docx_to_md_processor import LiteDocxToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import LitePdfToMdProcessor
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.pptx_markdown_processor import PptxMarkdownProcessor
from knowledge_flow_backend.core.processors.input.text_markdown_processor.text_markdown_processor import TextMarkdownProcessor
from knowledge_flow_backend.core.processors.input.markdown_markdown_processor.markdown_markdown_processor import (
    MarkdownMarkdownProcessor,
)
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import (
    PdfMarkdownProcessor,
)

from .runner import ProcessorSpec


def default_registry() -> Dict[str, ProcessorSpec]:
    specs: List[ProcessorSpec] = [
        ProcessorSpec(
            id="pdf_standard_docling",
            kind="standard",
            factory=lambda: PdfMarkdownProcessor(),
            display_name="PDF → MD (Standard/Docling)",
            file_types=[".pdf"],
        ),
        ProcessorSpec(
            id="pdf_lite_markitdown",
            kind="lite",
            factory=lambda: LitePdfToMdProcessor(),
            display_name="PDF → MD (Lite/MarkItDown)",
            file_types=[".pdf"],
        ),
        ProcessorSpec(
            id="docx_standard_pandoc",
            kind="standard",
            factory=lambda: DocxMarkdownProcessor(),
            display_name="DOCX → MD (Standard/Pandoc)",
            file_types=[".docx"],
        ),
        ProcessorSpec(
            id="docx_lite_markitdown",
            kind="lite",
            factory=lambda: LiteDocxToMdProcessor(),
            display_name="DOCX → MD (Lite/MarkItDown)",
            file_types=[".docx"],
        ),
        ProcessorSpec(
            id="pptx_standard_pandoc",
            kind="standard",
            factory=lambda: PptxMarkdownProcessor(),
            display_name="PPTX → MD (Standard/Pandoc)",
            file_types=[".pptx"],
        ),
        ProcessorSpec(
            id="text_standard_plain",
            kind="standard",
            factory=lambda: TextMarkdownProcessor(),
            display_name="Text → MD (Standard)",
            file_types=[".txt"],
        ),
        ProcessorSpec(
            id="markdown_standard_passthrough",
            kind="standard",
            factory=lambda: MarkdownMarkdownProcessor(),
            display_name="Markdown → MD (Standard)",
            file_types=[".md"],
        ),
    ]

    return {s.id: s for s in specs}
