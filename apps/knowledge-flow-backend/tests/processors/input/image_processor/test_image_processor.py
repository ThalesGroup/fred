from pathlib import Path
from types import SimpleNamespace

from knowledge_flow_backend.core.processors.input.common.image_describer import IMAGE_DESCRIPTION_UNAVAILABLE
from knowledge_flow_backend.core.processors.input.image_processor.image_processor import ImageProcessor

_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_MODULE = "knowledge_flow_backend.core.processors.input.image_processor.image_processor"


def _convert(tmp_path: Path, image_name: str = "Nvidia_logo.png") -> str:
    image_path = tmp_path / image_name
    image_path.write_bytes(_ONE_PIXEL_PNG)
    output_dir = tmp_path / "out"
    result = ImageProcessor().convert_file_to_markdown(image_path, output_dir, document_uid=None)
    return Path(result["md_file"]).read_text(encoding="utf-8")


def test_image_processor_keeps_filename_markdown_without_vision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(f"{_MODULE}.get_configuration", lambda: SimpleNamespace(vision_model=None))

    markdown = _convert(tmp_path)

    assert "# Nvidia_logo" in markdown
    assert 'Search for "Nvidia_logo"' in markdown
    assert "Vision summary" not in markdown


def test_image_processor_appends_vision_summary_when_available(tmp_path: Path, monkeypatch) -> None:
    class FakeDescriber:
        def describe(self, data_url: str) -> str:
            assert data_url.startswith("data:image/png;base64,")
            return "There is an image showing a green logo on a black background."

    monkeypatch.setattr(f"{_MODULE}.get_configuration", lambda: SimpleNamespace(vision_model=object()))
    monkeypatch.setattr(f"{_MODULE}.build_image_describer", lambda _: FakeDescriber())

    markdown = _convert(tmp_path)

    assert "## Vision summary" in markdown
    assert "green logo on a black background" in markdown
    assert "# Nvidia_logo" in markdown


def test_image_processor_skips_vision_section_when_description_unavailable(tmp_path: Path, monkeypatch) -> None:
    class FailingDescriber:
        def describe(self, _: str) -> str:
            return IMAGE_DESCRIPTION_UNAVAILABLE

    monkeypatch.setattr(f"{_MODULE}.get_configuration", lambda: SimpleNamespace(vision_model=object()))
    monkeypatch.setattr(f"{_MODULE}.build_image_describer", lambda _: FailingDescriber())

    markdown = _convert(tmp_path)

    assert "Vision summary" not in markdown
    assert 'Search for "Nvidia_logo"' in markdown


def test_image_processor_builds_describer_once_across_documents(tmp_path: Path, monkeypatch) -> None:
    build_calls = []

    class FakeDescriber:
        def describe(self, _: str) -> str:
            return "There is an image showing a single pixel."

    def _build(_) -> FakeDescriber:
        build_calls.append(1)
        return FakeDescriber()

    monkeypatch.setattr(f"{_MODULE}.get_configuration", lambda: SimpleNamespace(vision_model=object()))
    monkeypatch.setattr(f"{_MODULE}.build_image_describer", _build)

    processor = ImageProcessor()
    for name in ("first.png", "second.png"):
        image_path = tmp_path / name
        image_path.write_bytes(_ONE_PIXEL_PNG)
        processor.convert_file_to_markdown(image_path, tmp_path / "out" / name, document_uid=None)

    assert len(build_calls) == 1
