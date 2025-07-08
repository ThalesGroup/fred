import pytest
from types import SimpleNamespace
from app.features.wip.input_processor_service import InputProcessorService


@pytest.fixture
def service():
    return InputProcessorService()


def test_extract_metadata_success(monkeypatch, tmp_path, service):
    fake_metadata = {"document_uid": "1234"}

    class FakeProcessor:
        def process_metadata(self, file_path, front_metadata):
            return fake_metadata

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: FakeProcessor())

    test_file = tmp_path / "test.docx"
    test_file.write_text("dummy content")
    metadata = service.extract_metadata(test_file, {})

    assert metadata == fake_metadata


def test_extract_metadata_missing_uid(monkeypatch, tmp_path, service):
    class FakeProcessor:
        def process_metadata(self, file_path, front_metadata):
            return {}  # No document_uid

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: FakeProcessor())

    test_file = tmp_path / "test.docx"
    test_file.write_text("dummy")

    with pytest.raises(ValueError, match="missing 'document_uid'"):
        service.extract_metadata(test_file, {})


def test_process_markdown(monkeypatch, tmp_path, service):
    class FakeMarkdownProcessor:
        def convert_file_to_markdown(self, file_path, output_dir):
            (output_dir / "file.md").write_text("# markdown")

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: FakeMarkdownProcessor())

    input_file = tmp_path / "test.md"
    input_file.write_text("dummy")

    service.process(tmp_path, input_file.name, {"doc": "meta"})
    output_file = tmp_path / "output" / "file.md"
    assert output_file.exists()
    assert output_file.read_text().startswith("# markdown")


def test_process_tabular(monkeypatch, tmp_path, service):
    import pandas as pd

    class FakeTabularProcessor:
        def convert_file_to_table(self, file_path):
            return pd.DataFrame({"col": [1, 2, 3]})

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: FakeTabularProcessor())

    input_file = tmp_path / "table.xlsx"
    input_file.write_text("dummy")

    service.process(tmp_path, input_file.name, {"doc": "meta"})
    output_file = tmp_path / "output" / "table.csv"
    assert output_file.exists()


def test_process_unknown_processor(monkeypatch, tmp_path, service):
    class UnknownProcessor:
        pass

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: UnknownProcessor())

    input_file = tmp_path / "weird.bin"
    input_file.write_text("data")

    with pytest.raises(RuntimeError, match="Unknown processor type"):
        service.process(tmp_path, input_file.name, {"meta": "data"})


@pytest.mark.asyncio
async def test_process_file_success(monkeypatch, tmp_path, service):
    class FakeProcessor:
        def process_metadata(self, file_path, front_metadata):
            return {"document_uid": "doc123"}

        def convert_file_to_markdown(self, file_path, output_dir):
            (output_dir / "file.md").write_text("# hello")

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: FakeProcessor())

    content = b"my file content"
    file = SimpleNamespace(filename="demo.docx", read=lambda: content)

    await service.process_file(file, {}, tmp_path)

    output_dir = tmp_path / "demo.docx" / "doc123"
    assert (output_dir / "metadata.json").exists()
    assert (output_dir / "file.md").exists()


@pytest.mark.asyncio
async def test_process_file_missing_uid(monkeypatch, tmp_path, service):
    class FakeProcessor:
        def process_metadata(self, file_path, front_metadata):
            return {}  # Missing UID

        def convert_file_to_markdown(self, file_path, output_dir):
            pass  # should not be called

    monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: FakeProcessor())

    content = b"my file content"
    file = SimpleNamespace(filename="missing.docx", read=lambda: content)

    with pytest.raises(RuntimeError, match="Missing document UID"):
        await service.process_file(file, {}, tmp_path)
