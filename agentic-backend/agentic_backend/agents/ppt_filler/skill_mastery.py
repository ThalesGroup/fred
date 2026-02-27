"""Skill mastery detection for CV images.

Supports two visual formats:
- Blue-dot bars (214x33px, 0-5 filled dots)
- Donut/ring charts (233x233px, 10 segments mapped to 1-5 scale)
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


def _find_ring_radii(
    data: bytes, width: int, height: int, cx: int, cy: int
) -> Optional[tuple[int, int]]:
    """Scan outward from center to find the ring's inner and outer radius.

    Scans at 4 diagonal angles to avoid landing on segment gaps,
    and returns the median inner/outer radius found.

    Returns:
        (inner_radius, outer_radius) or None if no ring detected.
    """
    max_r = min(cx, cy, width - cx, height - cy)
    scan_angles = [math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4]
    inner_hits: list[int] = []
    outer_hits: list[int] = []

    for angle in scan_angles:
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        inner = None
        last_r = 0
        found_outer = False
        for r in range(1, max_r):
            x = int(cx + r * cos_a)
            y = int(cy + r * sin_a)
            if not (0 <= x < width and 0 <= y < height):
                break
            i = (y * width + x) * 3
            pr, pg, pb = data[i], data[i + 1], data[i + 2]
            is_white = pr > 230 and pg > 230 and pb > 230
            last_r = r
            if inner is None:
                if not is_white:
                    inner = r
            else:
                if is_white:
                    outer_hits.append(r - 1)
                    inner_hits.append(inner)
                    found_outer = True
                    break
        if inner is not None and not found_outer:
            outer_hits.append(last_r)
            inner_hits.append(inner)

    if not inner_hits:
        return None
    inner_hits.sort()
    outer_hits.sort()
    mid = len(inner_hits) // 2
    inner_r = inner_hits[mid]
    outer_r = outer_hits[mid]
    if outer_r - inner_r < 3:
        return None
    return (inner_r, outer_r)


def count_donut_segments(img: Image.Image) -> Optional[int]:
    """Count filled (blue) segments in a 10-segment donut chart.

    Samples at the center of each 36-degree arc along the mid-radius
    of the ring. Maps the count to mastery 1-5 (filled // 2).

    Returns:
        Mastery level (1-5) or None if not a valid donut chart.
    """
    rgb = img.convert("RGB")
    width, height = rgb.size
    data = rgb.tobytes()
    cx, cy = width // 2, height // 2

    radii = _find_ring_radii(data, width, height, cx, cy)
    if radii is None:
        return None
    inner_r, outer_r = radii
    mid_r = (inner_r + outer_r) // 2

    filled = 0
    for seg in range(10):
        angle = math.radians(seg * 36)
        sx = int(cx + mid_r * math.cos(angle))
        sy = int(cy + mid_r * math.sin(angle))
        if not (0 <= sx < width and 0 <= sy < height):
            continue
        i = (sy * width + sx) * 3
        if _is_blue(data[i], data[i + 1], data[i + 2]):
            filled += 1

    if filled <= 0 or filled > 10 or filled % 2 != 0:
        return None
    return filled // 2


def extract_mastery_from_image(image_data: bytes) -> Optional[int]:
    """Open raw image bytes and detect skill mastery from dots or donut chart.

    Returns:
        Mastery level (0-5) if the image is a skill indicator, None otherwise.
    """
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            if img.size == (214, 33):
                return count_filled_dots(img)
            if img.size == (233, 233):
                return count_donut_segments(img)
            return None
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
