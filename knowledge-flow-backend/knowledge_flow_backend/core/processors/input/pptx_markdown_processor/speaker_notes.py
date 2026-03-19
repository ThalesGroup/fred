from __future__ import annotations

from typing import Optional


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
            if not getattr(shape, "has_text_frame", False):
                continue

            text_frame = getattr(shape, "text_frame", None)
            if text_frame is None:
                continue

            text = str(getattr(text_frame, "text", "")).strip()
            if text:
                texts.append(text)

        if not texts:
            return None

        content = "\n\n".join(texts).strip()
        return content or None
    except Exception:
        return None
