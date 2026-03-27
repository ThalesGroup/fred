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

"""Formats extracted PPTX slide content as Markdown."""

from __future__ import annotations

from typing import List

from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils.pptx_native_slide_extractor import (
    NativeSlideContent,
)


def format_slide_markdown(
    content: NativeSlideContent,
    visual_enrichment: str | None = None,
) -> str:
    lines: List[str] = []

    if content.title:
        lines.append(f"## Slide {content.slide_number}: {content.title}")
    else:
        lines.append(f"## Slide {content.slide_number}")
    lines.append("")

    if content.subtitle:
        lines.append("### Subtitle")
        lines.append(content.subtitle)
        lines.append("")

    if content.bullets:
        lines.append("### Key Points")
        lines.extend(content.bullets)
        lines.append("")

    if content.raw_text_blocks:
        lines.append("### Additional Text")
        lines.extend(content.raw_text_blocks)
        lines.append("")

    if content.tables:
        lines.append("### Tables")
        for idx, table_md in enumerate(content.tables, start=1):
            if len(content.tables) > 1:
                lines.append(f"#### Table {idx}")
            lines.append(table_md)
            lines.append("")

    if content.notes:
        lines.append("### Speaker Notes")
        lines.append(content.notes)
        lines.append("")

    if visual_enrichment:
        lines.append("### Visual Enrichment")
        lines.append(visual_enrichment)
        lines.append("")

    return "\n".join(lines).strip()
