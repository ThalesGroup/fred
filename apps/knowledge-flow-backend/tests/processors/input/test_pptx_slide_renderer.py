"""Exercise the PDFium child process, including failure and concurrent decks."""

import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils import pptx_slide_renderer as renderer


@pytest.fixture
def deck_pdf(tmp_path):
    path = tmp_path / "deck.pdf"
    doc = canvas.Canvas(str(path), pagesize=(600, 800))
    for n in range(3):
        doc.drawString(40, 740, f"Slide {n + 1}")
        doc.showPage()
    doc.save()
    return path


def test_selected_pages_are_opaque_and_twice_pdf_size(deck_pdf, tmp_path):
    paths = renderer.render_pdf_pages_to_png(deck_pdf, [3, 0, 2, 99, 3], tmp_path / "png")
    assert list(paths) == [3, 2]
    for n, path in paths.items():
        assert path.name == f"slide_{n:03d}.png"
        with Image.open(path) as image:
            assert image.size == (1200, 1600)
            assert image.mode == "RGB"
            assert image.getpixel((0, 0)) == (255, 255, 255)


def test_concurrent_decks_have_independent_native_state(deck_pdf, tmp_path):
    def render(n):
        return renderer.render_pdf_pages_to_png(deck_pdf, [1, 2, 3], tmp_path / str(n))

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(len(result) == 3 for result in pool.map(render, range(4)))


def test_invalid_pdf_fails_visibly(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_text("broken")
    with pytest.raises(subprocess.CalledProcessError):
        renderer.render_pdf_pages_to_png(broken, [1], tmp_path / "png")


def test_timeout_kills_and_reaps_child(deck_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(renderer, "RENDER_TIMEOUT_SECONDS", 0.000001)
    with pytest.raises(subprocess.TimeoutExpired):
        renderer.render_pdf_pages_to_png(deck_pdf, [1], tmp_path / "png")
