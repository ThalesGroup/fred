"""Tests for skill mastery detection (blue dots and donut charts)."""

import io
import math

import pytest
from PIL import Image

from agentic_backend.agents.ppt_filler.skill_mastery import (
    count_donut_segments,
    count_filled_dots,
    extract_mastery_from_image,
    inject_mastery_alt_text,
    is_raster_image,
    parse_image_refs,
)

# Target blue used in CV skill bars.
BLUE = (0, 174, 199)
GREY = (200, 200, 200)
WHITE = (255, 255, 255)


def _make_skill_bar(filled: int) -> Image.Image:
    """Create a synthetic 214x33 skill-bar image with `filled` blue dots."""
    img = Image.new("RGB", (214, 33), color=GREY)
    dot_width = 30
    gap = (214 - 5 * dot_width) // 6  # spacing between dots

    for i in range(filled):
        x_start = gap + i * (dot_width + gap)
        for x in range(x_start, x_start + dot_width):
            for y in range(5, 28):  # vertical band in the middle
                img.putpixel((x, y), BLUE)

    return img


def _image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestCountFilledDots:
    def test_zero_dots(self):
        img = Image.new("RGB", (214, 33), color=GREY)
        assert count_filled_dots(img) == 0

    @pytest.mark.parametrize("filled", [1, 2, 3, 4, 5])
    def test_filled_dots(self, filled):
        img = _make_skill_bar(filled)
        assert count_filled_dots(img) == filled


class TestExtractMasteryFromImage:
    def test_skill_bar_detected(self):
        img = _make_skill_bar(3)
        data = _image_to_bytes(img)
        assert extract_mastery_from_image(data) == 3

    def test_wrong_size_returns_none(self):
        img = Image.new("RGB", (100, 100), color=BLUE)
        data = _image_to_bytes(img)
        assert extract_mastery_from_image(data) is None

    def test_invalid_image_returns_none(self):
        assert extract_mastery_from_image(b"not an image") is None


class TestIsRasterImage:
    @pytest.mark.parametrize("name", ["img.png", "photo.JPG", "pic.jpeg", "img.webp"])
    def test_raster(self, name):
        assert is_raster_image(name) is True

    @pytest.mark.parametrize("name", ["icon.svg", "chart.emf", "doc.pdf", "noext"])
    def test_non_raster(self, name):
        assert is_raster_image(name) is False


class TestParseImageRefs:
    def test_extracts_refs(self):
        html = (
            '<img src="knowledge-flow/v1/markdown/uid-123/media/image1.png" />'
            '<img src="knowledge-flow/v1/markdown/uid-456/media/image2.jpg" />'
        )
        refs = parse_image_refs(html)
        assert ("uid-123", "image1.png") in refs
        assert ("uid-456", "image2.jpg") in refs

    def test_no_matches(self):
        assert parse_image_refs("no images here") == []


class TestInjectMasteryAltText:
    def test_adds_alt_text(self):
        html = '<img src="knowledge-flow/v1/markdown/uid/media/img1.png">'
        result = inject_mastery_alt_text(html, {"img1.png": 3})
        assert 'alt="3/5 de maitrise"' in result

    def test_replaces_existing_alt(self):
        html = '<img src="knowledge-flow/v1/markdown/uid/media/img1.png" alt="old">'
        result = inject_mastery_alt_text(html, {"img1.png": 4})
        assert 'alt="4/5 de maitrise"' in result
        assert "old" not in result

    def test_no_match_unchanged(self):
        html = '<img src="knowledge-flow/v1/markdown/uid/media/other.png">'
        result = inject_mastery_alt_text(html, {"img1.png": 3})
        assert result == html


# ---------- Donut chart tests ----------

DONUT_SIZE = 233


def _make_donut_chart(filled: int, size: int = DONUT_SIZE) -> Image.Image:
    """Create a synthetic donut chart with `filled` blue segments out of 10.

    Segments are centered at 0°, 36°, 72°, ... (matching real CV images).
    Each segment spans 33° with a 3° gap between segments.
    """
    img = Image.new("RGB", (size, size), color=WHITE)
    cx, cy = size // 2, size // 2
    outer_r = int(size * 0.45)
    inner_r = int(size * 0.30)
    segment_degrees = 33  # 36 - 3 degree gap
    half_seg = segment_degrees / 2  # 16.5° on each side of center

    for x in range(size):
        for y in range(size):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            if inner_r <= dist <= outer_r:
                angle = math.degrees(math.atan2(dy, dx)) % 360
                # Find which segment center (0°, 36°, 72°, ...) is closest
                seg_idx = round(angle / 36) % 10
                seg_center = seg_idx * 36
                # Angular distance to segment center
                diff = abs(((angle - seg_center + 180) % 360) - 180)
                if diff <= half_seg:
                    if seg_idx < filled:
                        img.putpixel((x, y), BLUE)
                    else:
                        img.putpixel((x, y), GREY)

    return img


class TestCountDonutSegments:
    @pytest.mark.parametrize(
        "filled,expected_mastery",
        [
            (2, 1),
            (4, 2),
            (6, 3),
            (8, 4),
            (10, 5),
        ],
    )
    def test_filled_segments(self, filled, expected_mastery):
        img = _make_donut_chart(filled)
        assert count_donut_segments(img) == expected_mastery

    def test_zero_filled_returns_none(self):
        img = _make_donut_chart(0)
        assert count_donut_segments(img) is None

    def test_non_donut_returns_none(self):
        img = Image.new("RGB", (DONUT_SIZE, DONUT_SIZE), color=WHITE)
        assert count_donut_segments(img) is None


class TestExtractMasteryDonutIntegration:
    def test_donut_chart_via_extract(self):
        img = _make_donut_chart(6)
        data = _image_to_bytes(img)
        assert extract_mastery_from_image(data) == 3

    def test_dot_bar_still_works(self):
        img = _make_skill_bar(3)
        data = _image_to_bytes(img)
        assert extract_mastery_from_image(data) == 3

    def test_random_233_image_returns_none(self):
        img = Image.new("RGB", (DONUT_SIZE, DONUT_SIZE), color=(128, 0, 0))
        data = _image_to_bytes(img)
        assert extract_mastery_from_image(data) is None
