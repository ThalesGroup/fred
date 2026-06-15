from pathlib import Path
from types import SimpleNamespace

from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor import (
    FastLiteImageProcessor,
)

_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_fast_lite_image_processor_uses_filename_fallback_without_vision(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "Screenshot_login_page.png"
    image_path.write_bytes(_ONE_PIXEL_PNG)

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor.get_configuration",
        lambda: SimpleNamespace(vision_model=None),
    )

    result = FastLiteImageProcessor().extract(image_path)

    assert result.document_name == "Screenshot_login_page.png"
    assert result.page_count == 1
    assert "Screenshot login page" in result.text
    assert "session-scoped retrieval" in result.text


def test_fast_lite_image_processor_appends_vision_summary_when_available(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(_ONE_PIXEL_PNG)

    class FakeDescriber:
        def describe(self, _: str) -> str:
            return "There is an image showing a login form and a submit button."

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor.get_configuration",
        lambda: SimpleNamespace(vision_model=object()),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_image_processor.build_image_describer",
        lambda _: FakeDescriber(),
    )

    result = FastLiteImageProcessor().extract(image_path)

    assert "Vision summary:" in result.text
    assert "login form and a submit button" in result.text
