from __future__ import annotations

from typing import List

from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.native_slide_extractor import (
    NativeSlideContent,
)


def format_slide_markdown(content: NativeSlideContent) -> str:
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

    return "\n".join(lines).strip()
