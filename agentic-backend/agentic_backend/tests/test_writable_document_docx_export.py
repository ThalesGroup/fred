from __future__ import annotations

import io

from docx import Document

from agentic_backend.core.writable_documents.docx_export import markdown_to_docx_bytes


def _read_paragraphs(data: bytes) -> list[tuple[str, str]]:
    doc = Document(io.BytesIO(data))
    return [
        ((p.style.name or "") if p.style is not None else "", p.text)
        for p in doc.paragraphs
    ]


def test_docx_is_valid_zip_with_title():
    data = markdown_to_docx_bytes("# Hello\n\nBody", title="My Doc")
    assert data[:2] == b"PK"  # docx is a zip
    paras = _read_paragraphs(data)
    assert ("Title", "My Doc") in paras
    assert ("Heading 1", "Hello") in paras


def test_docx_maps_common_markdown_constructs():
    md = (
        "# H1\n\n"
        "Some **bold** and *italic* and `code`.\n\n"
        "- bullet one\n"
        "- bullet two\n\n"
        "1. first\n"
        "2. second\n\n"
        "```\n"
        "code line 1\n"
        "code line 2\n"
        "```\n\n"
        "Final soft\n"
        "wrapped paragraph."
    )
    paras = _read_paragraphs(markdown_to_docx_bytes(md))
    styles = [s for s, _ in paras]
    texts = [t for _, t in paras]

    assert ("Heading 1", "H1") in paras
    # Inline markers are stripped; text content preserved in a normal paragraph.
    assert "Some bold and italic and code." in texts
    assert styles.count("List Bullet") == 2
    assert styles.count("List Number") == 2
    # Fenced code block content kept (joined with newlines) in one paragraph.
    assert any("code line 1\ncode line 2" == t for t in texts)
    # Soft-wrapped lines merged into a single paragraph.
    assert "Final soft wrapped paragraph." in texts


def test_docx_handles_empty_content():
    data = markdown_to_docx_bytes("", title="Empty")
    assert data[:2] == b"PK"
    assert ("Title", "Empty") in _read_paragraphs(data)


def test_bold_run_is_marked_bold():
    data = markdown_to_docx_bytes("This is **strong** text")
    doc = Document(io.BytesIO(data))
    runs = [r for p in doc.paragraphs for r in p.runs]
    bold_run = next((r for r in runs if r.text == "strong"), None)
    assert bold_run is not None
    assert bold_run.bold is True
