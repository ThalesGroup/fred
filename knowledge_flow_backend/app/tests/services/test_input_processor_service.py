# app/tests/features/test_input_processor_service.py

import pytest
from types import SimpleNamespace
from app.features.wip.input_processor_service import InputProcessorService


class TestInputProcessorService:

    @pytest.fixture
    def service(self):
        return InputProcessorService()

    def test_extract_metadata_success(self, tmp_path, service):
        test_file = tmp_path / "test.md"
        test_file.write_text("dummy content")

        metadata = service.extract_metadata(test_file, {})
        assert "document_uid" in metadata
        assert metadata["title"] == "test-markdown"
        assert metadata["document_name"] == "test.md"

    def test_extract_metadata_missing_uid(self, tmp_path, service):
        # This should no longer raise because `TestMarkdownProcessor` always adds a UID
        test_file = tmp_path / "test.md"
        test_file.write_text("dummy")
        metadata = service.extract_metadata(test_file, {})
        assert "document_uid" in metadata

    def test_process_markdown(self, tmp_path, service):
        input_file = tmp_path / "test.md"
        input_file.write_text("dummy")

        service.process(tmp_path, input_file.name, {"doc": "meta"})
        output_file = tmp_path / "output" / "file.md"
        assert output_file.exists()
        assert output_file.read_text() == "# Test Markdown Content"

    def test_process_tabular(self, tmp_path, service):
        input_file = tmp_path / "table.xlsx"
        input_file.write_text("dummy")

        service.process(tmp_path, input_file.name, {"doc": "meta"})
        output_file = tmp_path / "output" / "table.csv"
        assert output_file.exists()
        content = output_file.read_text()
        assert "col1" in content
        assert "1" in content
        assert "A" in content

    def test_process_unknown_processor(self, monkeypatch, tmp_path, service):
        # Forcefully override with unknown type (not needed if registry is correct)
        class UnknownProcessor:
            pass

        monkeypatch.setattr(service.context, "get_input_processor_instance", lambda ext: UnknownProcessor())

        input_file = tmp_path / "weird.bin"
        input_file.write_text("data")

        with pytest.raises(RuntimeError, match="Unknown processor type"):
            service.process(tmp_path, input_file.name, {"meta": "data"})

    @pytest.mark.asyncio
    async def test_process_file_success(self, tmp_path, service):
        content = b"hello world"
        file = SimpleNamespace(filename="demo.md", read=lambda: content)

        await service.process_file(file, {}, tmp_path)

        output_dir = tmp_path / "demo.md"
        assert output_dir.exists()
        # Expect 1 UID subdir
        subdirs = list(output_dir.iterdir())
        assert len(subdirs) == 1
        uid_dir = subdirs[0]
        assert (uid_dir / "metadata.json").exists()
        assert (uid_dir / "file.md").exists()
        assert (uid_dir / "file.md").read_text() == "# Test Markdown Content"

