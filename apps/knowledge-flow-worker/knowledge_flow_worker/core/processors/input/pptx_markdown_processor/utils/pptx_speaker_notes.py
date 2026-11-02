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

"""Extracts speaker notes from PPTX slides."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _is_page_number_candidate(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return value.isdigit() and 1 <= len(value) <= 3


def _is_notes_body_shape(shape) -> bool:
    """
    Keep only the real speaker-notes body placeholder.
    Ignore slide number and other system placeholders.
    """
    try:
        placeholder_format = getattr(shape, "placeholder_format", None)
        if placeholder_format is None:
            return False

        ph_type = getattr(placeholder_format, "type", None)
        if ph_type is None:
            return False

        # 2 = BODY in python-pptx PP_PLACEHOLDER
        return int(ph_type) == 2
    except Exception:
        return False


def extract_speaker_notes(slide) -> Optional[str]:
    """
    Extract speaker notes text from a PPTX slide.
    Returns None when notes are missing or empty.
    """
    try:
        notes_slide = getattr(slide, "notes_slide", None)
        if notes_slide is None:
            return None

        texts: list[str] = []
        for shape in getattr(notes_slide, "shapes", []):
            if not _is_notes_body_shape(shape):
                continue
            if not getattr(shape, "has_text_frame", False):
                continue

            text_frame = getattr(shape, "text_frame", None)
            if text_frame is None:
                continue

            text = str(getattr(text_frame, "text", "")).strip()
            if not text:
                continue
            if _is_page_number_candidate(text):
                continue
            texts.append(text)

        if not texts:
            return None

        content = "\n\n".join(texts).strip()
        return content or None
    except (AttributeError, TypeError) as exc:
        logger.debug("Failed to extract speaker notes due to expected error: %s", exc)
        return None
    except Exception:
        logger.debug("Unexpected error while extracting speaker notes", exc_info=True)
        return None
