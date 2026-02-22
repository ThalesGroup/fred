"""Blue-dot skill mastery counter for CV skill bar images.

CV templates represent skill mastery as a row of blue dots (0-5 filled).
This module detects those images by their fixed dimensions and counts
the filled dots using colour distance from the target blue.
"""

import io
import logging
import math
import re
from typing import Optional

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


def _is_blue(r: int, g: int, b: int) -> bool:
    """Return True if the pixel is close enough to the target blue RGB(0, 174, 199)."""
    dist = math.sqrt((r - 0) ** 2 + (g - 174) ** 2 + (b - 199) ** 2)
    return dist < 60


def count_filled_dots(img: Image.Image) -> int:
    """Count the number of filled blue dots in a skill-bar image.

    Args:
        img: A PIL Image, expected to be 214x33 pixels.

    Returns:
        Number of filled dots (0-5).
    """
    rgb = img.convert("RGB")
    width, height = rgb.size
    data = rgb.tobytes()

    cols_with_blue: list[int] = []
    for x in range(width):
        blue_count = 0
        for y in range(height):
            i = (y * width + x) * 3
            if _is_blue(data[i], data[i + 1], data[i + 2]):
                blue_count += 1
        if blue_count > 5:
            cols_with_blue.append(x)

    if not cols_with_blue:
        return 0

    filled = 1
    for i in range(1, len(cols_with_blue)):
        if cols_with_blue[i] - cols_with_blue[i - 1] > 3:
            filled += 1

    return filled


def extract_mastery_from_image(image_data: bytes) -> Optional[int]:
    """Open raw image bytes, check if it's a skill bar (214x33), and return mastery.

    Returns:
        Mastery level (0-5) if the image is a skill bar, None otherwise.
    """
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            if img.size != (214, 33):
                return None
            return count_filled_dots(img)
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("[skill_mastery] Unreadable image: %s", exc)
        return None


def is_raster_image(filename: str) -> bool:
    """Return True if the filename has a raster image extension."""
    raster_suffixes = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
    }
    dot = filename.rfind(".")
    if dot == -1:
        return False
    return filename[dot:].lower() in raster_suffixes


def parse_image_refs(chunks_text: str) -> list[tuple[str, str]]:
    """Extract (document_uid, media_filename) pairs from <img> tags in markdown.

    Matches src URLs like: knowledge-flow/v1/markdown/{uid}/media/{filename}
    """
    pattern = re.compile(
        r'<img[^>]*\bsrc="[^"]*knowledge-flow/v1/markdown/([^"]+)/media/([^"]+)"[^>]*>'
    )
    return pattern.findall(chunks_text)


def inject_mastery_alt_text(chunks_text: str, mastery_map: dict[str, int]) -> str:
    """Replace alt text of <img> tags whose filename has a known mastery level."""
    for filename, level in mastery_map.items():
        alt_text = f"{level}/5 de maitrise"
        pattern = re.compile(rf'(<img[^>]*\bsrc="[^"]*/{re.escape(filename)}"[^>]*)>')

        def _repl(match: re.Match, alt=alt_text) -> str:
            tag = match.group(1)
            if "alt=" in tag:
                tag = re.sub(r'alt="[^"]*"', f'alt="{alt}"', tag)
            else:
                tag = f'{tag} alt="{alt}"'
            return tag + ">"

        chunks_text = pattern.sub(_repl, chunks_text)

    return chunks_text
