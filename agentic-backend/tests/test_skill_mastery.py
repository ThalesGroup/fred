"""Tests for the blue-dot skill mastery counter."""

import io

import pytest
from PIL import Image

from agentic_backend.agents.ppt_filler.skill_mastery import (
    count_filled_dots,
    extract_mastery_from_image,
    inject_mastery_alt_text,
    is_raster_image,
    parse_image_refs,
)

# Target blue used in CV skill bars.
BLUE = (0, 174, 199)
GREY = (200, 200, 200)


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
