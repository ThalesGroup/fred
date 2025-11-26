from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fred_core.processors import (
    DocumentMetadata,
    Identity,
    LibraryDocumentInput,
    LibraryProcessorBundle,
    SourceInfo,
    SourceType,
)

from cir.cir_library_output_processor import CirLibraryOutputProcessor


def test_process_library_inline_bundle(monkeypatch, tmp_path):
    # Isolate temporary workspace for the processor
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    processor = CirLibraryOutputProcessor()

    meta = DocumentMetadata(
        identity=Identity(document_name="demo.md", document_uid="uid-1"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
    )
    doc_input = LibraryDocumentInput(
        file_path="demo.md", metadata=meta, preview_markdown="# Demo\nThis is a test doc."
    )

    updated, bundle = processor.process_library(
        documents=[doc_input],
        library_tag="demo",
        request=None,  # inline bundle path
    )

    # Metadata updated and extension populated
    assert len(updated) == 1
    ext = updated[0].extensions.get("hipporag", {})
    assert ext.get("status") == "success"
    assert ext.get("document_count") == 1
    assert ext.get("corpus_size") == 1

    # Bundle information returned inline
    assert isinstance(bundle, LibraryProcessorBundle)
    assert bundle.status == "success"
    assert bundle.bundle_b64
    assert bundle.bundle_size_bytes and bundle.bundle_size_bytes > 0

    # Bundle files were written under the isolated TMPDIR
    work_root = Path(tempfile.gettempdir()) / "fred-hipporag"
    assert work_root.exists()

    # Clean up generated artifacts
    shutil.rmtree(work_root, ignore_errors=True)
