from pathlib import Path

import pytest

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
)
from knowledge_flow_backend.core.processing_pipeline import ProcessingPipeline
from knowledge_flow_backend.core.processors.input.common.base_input_processor import (
    BaseMarkdownProcessor,
    InputConversionError,
)


class FailingMarkdownProcessor(BaseMarkdownProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        return {"document_name": file_path.name}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        return {
            "status": "error",
            "message": "simulated conversion failure",
            "md_file": None,
        }


def _metadata_for(file_name: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=file_name, document_uid="test-doc-uid"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.PDF),
    )


def test_process_input_raises_when_preview_is_missing(tmp_path: Path):
    input_file = tmp_path / "broken.pdf"
    input_file.write_bytes(b"%PDF-1.4 test")

    output_dir = tmp_path / "output"
    metadata = _metadata_for(input_file.name)
    pipeline = ProcessingPipeline(
        name="test",
        input_processors={".pdf": FailingMarkdownProcessor()},
        output_processors={},
    )

    with pytest.raises(InputConversionError, match="reported status='error'"):
        pipeline.process_input(input_path=input_file, output_dir=output_dir, metadata=metadata)
