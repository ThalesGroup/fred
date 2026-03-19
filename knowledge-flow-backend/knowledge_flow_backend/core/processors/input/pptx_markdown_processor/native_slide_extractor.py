from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.shape_ordering import (
    sort_shapes_reading_order,
)
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.speaker_notes import (
    extract_speaker_notes,
)


@dataclass
class NativeSlideContent:
    slide_number: int
    title: Optional[str] = None
    subtitle: Optional[str] = None
    bullets: List[str] = field(default_factory=list)
    raw_text_blocks: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    notes: Optional[str] = None


def _escape_pipes(text: str) -> str:
    return text.replace("|", r"\|")


def _clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip()


def _text_frame_lines(text_frame: Any) -> List[str]:
    lines: List[str] = []

    for para in getattr(text_frame, "paragraphs", []):
        text = _clean_text(getattr(para, "text", "") or "")
        if not text:
            continue

        level = int(getattr(para, "level", 0) or 0)
        indent = "  " * max(0, level)

        if level > 0:
            lines.append(f"{indent}- {text}")
        else:
            lines.append(f"{indent}{text}")

    return lines


def _table_to_markdown(table: Any) -> str:
    try:
        rows = len(table.rows)
        cols = len(table.columns)
    except Exception:
        return ""

    if rows <= 0 or cols <= 0:
        return ""

    def cell_text(r: int, c: int) -> str:
        try:
            cell = table.cell(r, c)
            raw = getattr(cell, "text", "") or ""
            return _escape_pipes(_clean_text(raw))
        except Exception:
            return ""

    header = [cell_text(0, c) or " " for c in range(cols)]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * cols) + " |",
    ]

    for r in range(1, rows):
        row = [cell_text(r, c) or " " for c in range(cols)]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines).strip()

def _extract_shape_text_lines(shape: Any) -> List[str]:
    has_text_frame = bool(getattr(shape, "has_text_frame", False))
    text_frame = getattr(shape, "text_frame", None)
    if has_text_frame and text_frame is not None:
        return _text_frame_lines(text_frame)

    text_value = _clean_text(getattr(shape, "text", "") or "")
    return [text_value] if text_value else []

def _is_title_candidate(lines: List[str]) -> bool:
    if len(lines) != 1:
        return False

    line = lines[0].strip()
    if not line:
        return False
    if line.startswith("- "):
        return False

    word_count = len(line.split())
    if word_count == 0 or word_count > 12:
        return False

    if len(line) > 120:
        return False

    return True

def _is_visual_list_item(line: str, title: Optional[str], subtitle: Optional[str]) -> bool:
    text = line.strip()
    if not text:
        return False

    if title and text == title:
        return False
    if subtitle and text == subtitle:
        return False

    if text.startswith("- "):
        return True

    word_count = len(text.split())
    char_count = len(text)

    # Reject very short visual fragments or decorative labels
    if char_count <= 3:
        return False

    # Reject most all-caps fragments that look like infographic labels
    if text.isupper() and word_count <= 5:
        return False

    # Good candidates: short business items, domain names, action labels
    if 1 <= word_count <= 6 and char_count <= 60:
        return True

    return False



def _find_fallback_title(slide: Any) -> Optional[str]:
    for shape in sort_shapes_reading_order(getattr(slide, "shapes", [])):
        lines = _extract_shape_text_lines(shape)
        if _is_title_candidate(lines):
            return lines[0].strip()
    return None

def _is_subtitle_candidate(lines: List[str], title: Optional[str], subtitle: Optional[str]) -> bool:
    if title is None or subtitle is not None:
        return False
    if len(lines) != 1:
        return False

    line = lines[0].strip()
    if not line or line.startswith("- "):
        return False

    word_count = len(line.split())

    # Avoid promoting a single short action word as subtitle
    if word_count == 1:
        return False

    return len(line) <= 120


def extract_native_slide_content(slide: Any, slide_number: int) -> NativeSlideContent:
    result = NativeSlideContent(slide_number=slide_number)
    result.notes = extract_speaker_notes(slide)

    title_shape = None
    try:
        title_shape = slide.shapes.title
        title_text = _clean_text(getattr(title_shape, "text", "") or "")
        if title_text:
            result.title = title_text
    except Exception:
        title_shape = None

    if not result.title:
        result.title = _find_fallback_title(slide)


    for shape in sort_shapes_reading_order(getattr(slide, "shapes", [])):
        if title_shape is not None and shape is title_shape:
            continue
        lines = _extract_shape_text_lines(shape)
        if result.title and lines and len(lines) == 1 and lines[0].strip() == result.title:
            continue

        has_table = bool(getattr(shape, "has_table", False))
        table = getattr(shape, "table", None)
        if has_table and table is not None:
            table_md = _table_to_markdown(table)
            if table_md:
                result.tables.append(table_md)
            continue

        has_text_frame = bool(getattr(shape, "has_text_frame", False))
        text_frame = getattr(shape, "text_frame", None)
        if has_text_frame and text_frame is not None:
            lines = _text_frame_lines(text_frame)
            if not lines:
                continue

            if _is_subtitle_candidate(lines, result.title, result.subtitle):
                result.subtitle = lines[0].strip()
                continue

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                if _is_visual_list_item(stripped, result.title, result.subtitle):
                    if stripped.startswith("- "):
                        result.bullets.append(stripped)
                    else:
                        result.bullets.append(f"- {stripped}")
                else:
                    result.raw_text_blocks.append(stripped)
            continue

        text_value = _clean_text(getattr(shape, "text", "") or "")
        if text_value:
            if result.title and result.subtitle is None and len(text_value) <= 120:
                result.subtitle = text_value
            elif _is_visual_list_item(text_value, result.title, result.subtitle):
                result.bullets.append(f"- {text_value}")
            else:
                result.raw_text_blocks.append(text_value)


    return result
