# Copyright Thales 2026
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

"""The Word/PowerPoint native preview: render to PDF once, serve it by byte range.

The viewer fetches a document through pdf.js, which issues one size probe plus a
range request per chunk. So the two things worth pinning down are that a document
is converted exactly ONCE however many requests arrive, and that the shared Range
resolution serves the exact window asked for — a viewer handed the wrong bytes
renders a corrupt document rather than failing visibly.
"""

import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fred_core.kpi import NoOpKPIWriter

from knowledge_flow_backend.features.content import content_service as content_service_module
from knowledge_flow_backend.features.content.content_controller import resolve_range_window
from knowledge_flow_backend.features.content.content_service import (
    ContentService,
    PdfRenderFailedError,
    PdfRenderUnsupportedError,
)

_USER = SimpleNamespace(uid="user-1")


class _FakeContentStore:
    """Document-scoped store holding the original file and any derived artifact."""

    def __init__(self, original: bytes) -> None:
        self._original = original
        self.derived: dict[str, bytes] = {}

    def get_content(self, document_uid: str) -> BytesIO:
        return BytesIO(self._original)

    def get_output_artifact(self, doc_path: str) -> bytes:
        if doc_path not in self.derived:
            raise FileNotFoundError(doc_path)
        return self.derived[doc_path]

    def put_output_artifact(self, doc_path: str, data: bytes, *, content_type: str) -> None:
        self.derived[doc_path] = data


def _build_service(document_name: str, original: bytes = b"fake source") -> ContentService:
    service = ContentService.__new__(ContentService)
    service.content_store = _FakeContentStore(original)
    service.metadata_store = SimpleNamespace(
        get_metadata_by_uid=_async(SimpleNamespace(document_name=document_name)),
    )
    service.rebac = SimpleNamespace(check_user_permission_or_raise=_async(None))
    service.kpi = NoOpKPIWriter()
    service._render_locks = {}
    return service


def _async(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("document_name", "suffix", "pdf_name"),
    [
        ("rapport.docx", ".docx", "rapport.pdf"),
        ("deck.pptx", ".pptx", "deck.pdf"),
        ("vieux.ppt", ".ppt", "vieux.pdf"),
        # The suffix check is case-insensitive; the served name keeps the original stem.
        ("DECK.PPTX", ".pptx", "DECK.pdf"),
    ],
)
async def test_office_document_is_converted_once_then_served_from_cache(monkeypatch, tmp_path, document_name, suffix, pdf_name) -> None:
    service = _build_service(document_name)
    conversions: list[str] = []

    def fake_convert(source_path, **kwargs):
        conversions.append(source_path.suffix)
        pdf_path = tmp_path / "out.pdf"
        pdf_path.write_bytes(b"%PDF-1.5 rendered")
        return pdf_path

    monkeypatch.setattr(content_service_module, "convert_office_file_to_pdf", fake_convert)

    first = await service.get_pdf_render(_USER, "doc-1")
    second = await service.get_pdf_render(_USER, "doc-1")

    assert first.content == second.content == b"%PDF-1.5 rendered"
    assert first.file_name == pdf_name
    assert first.cached and second.cached
    # The second call must hit the cache: LibreOffice runs once, not once per request.
    assert conversions == [suffix]
    assert service.content_store.derived == {"doc-1/output/render.pdf": b"%PDF-1.5 rendered"}


@pytest.mark.asyncio
async def test_uncacheable_render_is_flagged_so_no_byte_range_is_cut_from_it(monkeypatch, tmp_path) -> None:
    """Each LibreOffice run stamps its own /CreationDate and /ID, so two renders of
    one document differ in length and offsets. When the render cannot be persisted,
    the caller has to know: serving a 206 out of bytes the next request will not
    reproduce hands the viewer windows from several files."""
    service = _build_service("rapport.docx")

    def failing_put(*args, **kwargs):
        raise RuntimeError("object store unavailable")

    service.content_store.put_output_artifact = failing_put
    monkeypatch.setattr(
        content_service_module,
        "convert_office_file_to_pdf",
        lambda source_path, **kwargs: _write_pdf(tmp_path / "out.pdf"),
    )

    render = await service.get_pdf_render(_USER, "doc-1")

    assert render.content == b"%PDF-1.5 rendered"
    assert render.cached is False


@pytest.mark.asyncio
async def test_concurrent_cold_opens_convert_the_document_once(monkeypatch, tmp_path) -> None:
    """Several viewers opening the same document must not each spawn LibreOffice."""
    service = _build_service("rapport.docx")
    conversions: list[str] = []

    def slow_convert(source_path, **kwargs):
        conversions.append(source_path.suffix)
        return _write_pdf(tmp_path / "out.pdf")

    monkeypatch.setattr(content_service_module, "convert_office_file_to_pdf", slow_convert)

    renders = await asyncio.gather(*(service.get_pdf_render(_USER, "doc-1") for _ in range(4)))

    assert len(conversions) == 1
    assert {r.content for r in renders} == {b"%PDF-1.5 rendered"}
    # The registry only exists to rendezvous concurrent cold opens; leaving one
    # Lock per document ever previewed would leak for the pod's lifetime.
    assert service._render_locks == {}


def _write_pdf(path):
    path.write_bytes(b"%PDF-1.5 rendered")
    return path


@pytest.mark.asyncio
async def test_pdf_document_is_pushed_back_to_the_stream_endpoint(monkeypatch) -> None:
    """A PDF needs no rendering, so this route refuses it rather than buffering it."""
    service = _build_service("facture.pdf", original=b"%PDF-1.5 original")

    def unexpected(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("a PDF must not be handed to LibreOffice")

    monkeypatch.setattr(content_service_module, "convert_office_file_to_pdf", unexpected)

    with pytest.raises(PdfRenderUnsupportedError, match="raw_content/stream"):
        await service.get_pdf_render(_USER, "doc-1")


@pytest.mark.asyncio
async def test_unsupported_format_is_rejected_rather_than_attempted(monkeypatch) -> None:
    service = _build_service("agence.xlsx")
    monkeypatch.setattr(content_service_module, "convert_office_file_to_pdf", lambda *a, **k: None)

    with pytest.raises(PdfRenderUnsupportedError):
        await service.get_pdf_render(_USER, "doc-1")


@pytest.mark.asyncio
async def test_conversion_failure_surfaces_as_render_failed(monkeypatch) -> None:
    service = _build_service("rapport.docx")
    # Best-effort contract: the helper returns None when soffice is missing/fails.
    monkeypatch.setattr(content_service_module, "convert_office_file_to_pdf", lambda *a, **k: None)

    with pytest.raises(PdfRenderFailedError):
        await service.get_pdf_render(_USER, "doc-1")

    assert service.content_store.derived == {}


class TestResolveRangeWindow:
    def test_no_range_header_means_the_whole_body(self) -> None:
        assert resolve_range_window(None, 100) is None
        assert resolve_range_window("pages=0-10", 100) is None

    def test_explicit_window_is_inclusive(self) -> None:
        assert resolve_range_window("bytes=10-19", 100) == (10, 19)

    def test_open_ended_range_runs_to_the_last_byte(self) -> None:
        assert resolve_range_window("bytes=90-", 100) == (90, 99)

    def test_end_past_eof_is_clamped(self) -> None:
        assert resolve_range_window("bytes=90-4000", 100) == (90, 99)

    def test_suffix_range_counts_back_from_the_end(self) -> None:
        assert resolve_range_window("bytes=-10", 100) == (90, 99)

    def test_suffix_longer_than_the_file_serves_it_whole(self) -> None:
        assert resolve_range_window("bytes=-4000", 100) == (0, 99)

    def test_start_past_eof_is_416_and_reports_the_real_size(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            resolve_range_window("bytes=100-120", 100)

        assert excinfo.value.status_code == 416
        # RFC 9110: an unsatisfiable range must tell the client the real length,
        # which the pre-refactor code built into a dict it then threw away.
        assert excinfo.value.headers == {"Content-Range": "bytes */100"}
