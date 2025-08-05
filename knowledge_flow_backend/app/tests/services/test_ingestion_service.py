import pytest
from app.features.ingestion.service import IngestionService
from app.common.document_structures import DocumentMetadata


@pytest.fixture
def sample_docx(tmp_path):
    sample_path = tmp_path / "sample.docx"
    sample_path.write_bytes(b"Dummy DOCX content")
    return sample_path


@pytest.fixture
def output_dir(tmp_path):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    return out_dir


def test_extract_and_save_metadata(sample_docx, metadata_store):
    service = IngestionService()

    # 🔍 Extract metadata
    metadata = service.extract_metadata(sample_docx, tags=["test"], source_tag="uploads")
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.document_uid is not None
    assert metadata.tags == ["test"]
    assert metadata.source_tag == "uploads"

    # 💾 Save metadata and reload it
    service.save_metadata(metadata)
    restored = service.get_metadata(metadata.document_uid)
    assert restored is not None
    assert restored.document_uid == metadata.document_uid
    assert restored.tags == ["test"]


def test_process_input(sample_docx, output_dir):
    service = IngestionService()
    metadata = service.extract_metadata(sample_docx, tags=["test"], source_tag="fred")

    # ⚙️ Process the file into output directory
    service.process_input(sample_docx, output_dir, metadata)

    # ✅ Check expected output
    output_file = output_dir / "output.md"
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_process_input_then_output(sample_docx, output_dir):
    service = IngestionService()
    metadata = service.extract_metadata(sample_docx, tags=["test"], source_tag="fred")

    # First process input
    service.process_input(sample_docx, output_dir, metadata)

    # Then process output
    result = service.process_output(sample_docx.name, output_dir, metadata)
    assert result is not None


def test_get_preview_file_fallback(sample_docx, output_dir):
    service = IngestionService()
    metadata = service.extract_metadata(sample_docx, tags=["test"], source_tag="fred")

    # Write a dummy preview
    preview = output_dir / "table.csv"
    preview.write_text("a,b,c\n1,2,3", encoding="utf-8")

    found = service.get_preview_file(metadata, output_dir)
    assert found.name == "table.csv"
