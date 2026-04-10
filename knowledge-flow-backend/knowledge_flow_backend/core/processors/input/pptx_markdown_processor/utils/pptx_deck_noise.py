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

"""Detects repeated deck-level text noise such as headers and footers."""

from __future__ import annotations

from collections import Counter
from math import ceil
from typing import Any, Iterable, Set


def _clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip()


def _extract_shape_lines(shape: Any) -> list[str]:
    has_text_frame = bool(getattr(shape, "has_text_frame", False))
    text_frame = getattr(shape, "text_frame", None)
    if has_text_frame and text_frame is not None:
        lines: list[str] = []
        for para in getattr(text_frame, "paragraphs", []):
            text = _clean_text(getattr(para, "text", "") or "")
            if text:
                lines.append(text)
        return lines

    text = _clean_text(getattr(shape, "text", "") or "")
    return [text] if text else []


def _looks_like_paragraph(text: str) -> bool:
    if not text:
        return False

    word_count = len(text.split())

    if word_count > 12:
        return True

    if len(text) > 80:
        return True

    punctuation_hits = sum(1 for ch in text if ch in ".,;:")
    if punctuation_hits >= 2:
        return True

    return False


def detect_repeated_noise_texts(slides: Iterable[Any], repetition_ratio: float = 0.4) -> Set[str]:
    slides_list = list(slides)
    slide_count = len(slides_list)
    if slide_count == 0:
        return set()

    min_occurrences = max(2, ceil(slide_count * repetition_ratio))
    counter: Counter[str] = Counter()

    for slide in slides_list:
        seen_in_slide: set[str] = set()

        for shape in getattr(slide, "shapes", []):
            for text in _extract_shape_lines(shape):
                if not text:
                    continue
                if _looks_like_paragraph(text):
                    continue

                seen_in_slide.add(text)

        for text in seen_in_slide:
            counter[text] += 1

    repeated_noise = {text for text, count in counter.items() if count >= min_occurrences}

    return repeated_noise
