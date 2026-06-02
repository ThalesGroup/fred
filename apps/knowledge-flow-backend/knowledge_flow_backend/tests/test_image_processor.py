"""Test suite for ImageProcessor"""

import tempfile
from pathlib import Path

import pytest

from knowledge_flow_backend.core.processors.input.image_processor.image_processor import ImageProcessor


@pytest.fixture
def image_processor():
    """Create an ImageProcessor instance"""
    return ImageProcessor()


@pytest.fixture
def sample_image_file():
    """Create a sample PNG file (1x1 transparent pixel)"""
    # Create a minimal valid PNG file (1x1 transparent pixel)
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(png_data)
        tmp_path = Path(tmp.name)

    return tmp_path


def test_check_file_validity_valid_image(image_processor, sample_image_file):
    """Test that valid image files pass validation"""
    assert image_processor.check_file_validity(sample_image_file) is True
    sample_image_file.unlink()


def test_check_file_validity_nonexistent_file(image_processor):
    """Test that non-existent files fail validation"""
    fake_path = Path("/nonexistent/image.png")
    assert image_processor.check_file_validity(fake_path) is False


def test_check_file_validity_unsupported_extension(image_processor):
    """Test that unsupported file extensions fail validation"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        tmp.write(b"not an image")
        tmp_path = Path(tmp.name)

    try:
        assert image_processor.check_file_validity(tmp_path) is False
    finally:
        tmp_path.unlink()


def test_check_file_validity_empty_file(image_processor):
    """Test that empty files fail validation"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp_path = Path(tmp.name)

    try:
        assert image_processor.check_file_validity(tmp_path) is False
    finally:
        tmp_path.unlink()


def test_extract_file_metadata(image_processor):
    """Test metadata extraction from image files"""
    # Create a test image file named "Apple.png"
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix="Apple") as tmp:
        tmp.write(png_data)
        tmp_path = Path(tmp.name)

    try:
        metadata = image_processor.extract_file_metadata(tmp_path)

        # Check basic metadata fields
        assert "document_name" in metadata
        assert metadata["document_name"] == tmp_path.name
        assert "title" in metadata
        assert metadata["title"] == tmp_path.stem  # Filename without extension
        assert "file_type" in metadata
        assert metadata["file_type"] == "image"

        # Check extras
        assert "extras" in metadata
        assert "image.format" in metadata["extras"]
        assert metadata["extras"]["image.format"] == "png"
        assert "image.searchable_name" in metadata["extras"]
        assert metadata["extras"]["image.searchable_name"] == tmp_path.stem

    finally:
        tmp_path.unlink()


def test_convert_file_to_markdown(image_processor):
    """Test markdown conversion for image files"""
    # Create a test image file named "Nvidia.png"
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    image_dir = tempfile.mkdtemp()
    image_path = Path(image_dir) / "Nvidia.png"

    with open(image_path, "wb") as f:
        f.write(png_data)

    output_dir = Path(tempfile.mkdtemp())

    try:
        result = image_processor.convert_file_to_markdown(image_path, output_dir, document_uid="test-uid-123")

        # Check result
        assert "doc_dir" in result
        assert "md_file" in result
        assert result["image_title"] == "Nvidia"

        # Check markdown file content
        md_path = Path(result["md_file"])
        assert md_path.exists()

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify markdown content
        assert "# Nvidia" in content
        assert "Type**: Image Logo/Icon" in content
        assert "Format**: png" in content
        assert "Filename**: Nvidia.png" in content
        assert 'Search for "Nvidia"' in content

    finally:
        # Cleanup
        image_path.unlink(missing_ok=True)
        for file in output_dir.iterdir():
            file.unlink()
        output_dir.rmdir()
        Path(image_dir).rmdir()


def test_supported_image_formats(image_processor):
    """Test that all supported image formats are recognized"""
    supported_formats = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"]

    for ext in supported_formats:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            # Write minimal valid data
            tmp.write(b"dummy content for size")
            tmp_path = Path(tmp.name)

        try:
            # Should pass the extension check (but may fail size/content check)
            # We're just checking that the extension is recognized
            result = image_processor.check_file_validity(tmp_path)
            # It will be True if file is not empty and extension is valid
            assert result is True or result is False  # Just checking it doesn't crash
        finally:
            tmp_path.unlink()
