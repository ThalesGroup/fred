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

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.processors.input.docx_markdown_processor import docx_markdown_processor as docx_module
from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import (
    DocxMarkdownProcessor,
)


@pytest.fixture
def processor():
    return DocxMarkdownProcessor()


@pytest.fixture
def samples_path():
    return Path(__file__).parent / "assets"


@pytest.mark.asyncio
async def test_process_docx_file(processor: DocxMarkdownProcessor, samples_path):
    test_docx_path = samples_path / "sample.docx"

    assert processor.check_file_validity(test_docx_path)
    metadata = processor.process_metadata(test_docx_path, [], "uploads")
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.document_uid
    assert metadata.document_name == "sample.docx"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        result = processor.convert_file_to_markdown(
            test_docx_path,
            output_dir,
            metadata.document_uid,  # ✅ now access attribute, not dict key
        )

        assert "md_file" in result
        assert output_dir.exists()


def test_convert_docx_skips_non_raster_media_in_cv_mode(processor: DocxMarkdownProcessor, tmp_path, monkeypatch):
    cv_dir = tmp_path / "path-without-marker"
    cv_dir.mkdir(parents=True, exist_ok=True)
    input_docx = cv_dir / "profile_cv.docx"
    input_docx.write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "output"
    document_uid = "doc-test-uid"

    def fake_subprocess_run(cmd, **_kwargs):
        if cmd and cmd[0] == "pandoc":
            md_path = Path(cmd[cmd.index("-o") + 1])
            media_dir = md_path.parent / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            Image.new("RGB", (214, 33), (0, 174, 199)).save(media_dir / "image1.png")
            (media_dir / "image9.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")

            md_path.write_text(
                f'<img src="{md_path.parent}/media/image1.png">\n<img src="{md_path.parent}/media/image9.svg">\n',
                encoding="utf-8",
            )
        return None

    monkeypatch.setattr(docx_module.subprocess, "run", fake_subprocess_run)

    result = processor.convert_file_to_markdown(input_docx, output_dir, document_uid)

    md_path = Path(result["md_file"])
    md_content = md_path.read_text(encoding="utf-8")

    assert md_path.exists()
    assert f"knowledge-flow/v1/markdown/{document_uid}/media/image1.png" in md_content
    assert f"knowledge-flow/v1/markdown/{document_uid}/media/image9.svg" in md_content


def test_convert_docx_skips_svg_for_cv_without_crash(processor: DocxMarkdownProcessor, tmp_path, monkeypatch):
    cv_dir = tmp_path / "path-without-marker"
    cv_dir.mkdir(parents=True, exist_ok=True)
    input_docx = cv_dir / "profile_cv.docx"
    input_docx.write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "output"
    document_uid = "doc-test-uid"

    def fake_subprocess_run(cmd, **_kwargs):
        if cmd and cmd[0] == "pandoc":
            md_path = Path(cmd[cmd.index("-o") + 1])
            media_dir = md_path.parent / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            (media_dir / "image9.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
            md_path.write_text(
                f'<img src="{md_path.parent}/media/image9.svg">\n',
                encoding="utf-8",
            )
        return None

    monkeypatch.setattr(docx_module.subprocess, "run", fake_subprocess_run)

    result = processor.convert_file_to_markdown(input_docx, output_dir, document_uid)
    md_content = Path(result["md_file"]).read_text(encoding="utf-8")

    assert f"knowledge-flow/v1/markdown/{document_uid}/media/image9.svg" in md_content
    assert 'image9.svg" alt=' not in md_content


def test_convert_docx_handles_many_image_extensions(processor: DocxMarkdownProcessor, tmp_path, monkeypatch):
    cv_dir = tmp_path / "path-without-marker"
    cv_dir.mkdir(parents=True, exist_ok=True)
    input_docx = cv_dir / "profile_cv.docx"
    input_docx.write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "output"
    document_uid = "doc-test-uid"

    tested_extensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
        ".svg",
        ".ico",
        ".avif",
        ".heic",
        ".jp2",
        ".wmf",
        ".emf",
    ]

    def fake_subprocess_run(cmd, **_kwargs):
        if cmd and cmd[0] == "pandoc":
            md_path = Path(cmd[cmd.index("-o") + 1])
            media_dir = md_path.parent / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            lines = []
            for ext in tested_extensions:
                media_file = media_dir / f"image_{ext[1:]}{ext}"
                if ext == ".svg":
                    media_file.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
                elif ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}:
                    Image.new("RGB", (214, 33), (0, 174, 199)).save(media_file)
                else:
                    media_file.write_bytes(b"not-an-image")
                lines.append(f'<img src="{md_path.parent}/media/{media_file.name}">')

            # Add a corrupt raster with supported extension to validate graceful skip.
            bad_jpg = media_dir / "image_bad.jpg"
            bad_jpg.write_bytes(b"corrupt-jpg")
            lines.append(f'<img src="{md_path.parent}/media/{bad_jpg.name}">')

            md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return None

        # Inkscape export path used by processor (EMF->SVG).
        export_arg = next((part for part in cmd if isinstance(part, str) and part.startswith("--export-filename=")), None)
        if export_arg:
            output_path = Path(export_arg.split("=", 1)[1])
            if output_path.suffix.lower() == ".svg":
                output_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
            elif output_path.suffix.lower() == ".png":
                Image.new("RGB", (214, 33), (0, 174, 199)).save(output_path)
        return None

    monkeypatch.setattr(docx_module, "which", lambda _name: "/usr/bin/inkscape")
    monkeypatch.setattr(docx_module.subprocess, "run", fake_subprocess_run)

    result = processor.convert_file_to_markdown(input_docx, output_dir, document_uid)
    md_content = Path(result["md_file"]).read_text(encoding="utf-8")

    assert f"knowledge-flow/v1/markdown/{document_uid}/media/image_svg.svg" in md_content
    assert f"knowledge-flow/v1/markdown/{document_uid}/media/image_emf.svg" in md_content
    assert 'alt="1/5 de maitrise"' in md_content


def test_convert_docx_does_not_enable_cv_mode_when_only_path_contains_cv(processor: DocxMarkdownProcessor, tmp_path, monkeypatch):
    cv_dir = tmp_path / "path-with-cv-marker"
    cv_dir.mkdir(parents=True, exist_ok=True)
    # Filename does not contain "cv" -> CV mode must not be triggered anymore.
    input_docx = cv_dir / "profile.docx"
    input_docx.write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "output"
    document_uid = "doc-test-uid"

    def fake_subprocess_run(cmd, **_kwargs):
        if cmd and cmd[0] == "pandoc":
            md_path = Path(cmd[cmd.index("-o") + 1])
            media_dir = md_path.parent / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            # Skill-bar-like image that would normally be annotated in CV mode.
            Image.new("RGB", (214, 33), (0, 174, 199)).save(media_dir / "image1.png")
            md_path.write_text(
                f'<img src="{md_path.parent}/media/image1.png">\n',
                encoding="utf-8",
            )
        return None

    monkeypatch.setattr(docx_module.subprocess, "run", fake_subprocess_run)

    result = processor.convert_file_to_markdown(input_docx, output_dir, document_uid)
    md_content = Path(result["md_file"]).read_text(encoding="utf-8")

    assert f"knowledge-flow/v1/markdown/{document_uid}/media/image1.png" in md_content
    assert 'alt="1/5 de maitrise"' not in md_content
