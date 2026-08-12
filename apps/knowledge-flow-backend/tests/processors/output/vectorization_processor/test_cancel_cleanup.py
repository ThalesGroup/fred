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

"""Cancelled vectorization self-cleans its partial vectors (issue #2315).

The compensation purge can run while the indexing thread is still writing, so
batches landing after the purge would be orphaned forever. The ordering-proof
fix is the thread deleting what it wrote as its last act before propagating
WorkCancelled — these tests lock in that behavior and that a cancel is not
reported as a failure (no error KPI, no VectorProcessingError wrapping).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from langchain_core.documents import Document

from knowledge_flow_backend.common.cancellation import WorkCancelled
from knowledge_flow_backend.core.processors.output.vectorization_processor import (
    vectorization_processor as vp_module,
)
from knowledge_flow_backend.core.processors.output.vectorization_processor.vectorization_processor import (
    VectorizationProcessor,
)


class _CancelledVectorStore:
    """Raises WorkCancelled on add (the checkpoint fired mid-indexing)."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def add_documents(self, chunks):
        raise WorkCancelled("vector indexing cancelled; abandoning the remaining work")

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        self.deleted.append(document_uid)


class _RecordingKpi:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def vectorization_result(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _metadata(uid: str = "doc-cancel-1") -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.md", document_uid=uid, modified=datetime.now(timezone.utc)),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads", date_added_to_kb=datetime.now(timezone.utc)),
        file=FileInfo(),
        tags=Tagging(tag_ids=[]),
    )


def _processor(store: _CancelledVectorStore, kpi: _RecordingKpi) -> VectorizationProcessor:
    # Bypass __init__: it builds real embedder/splitter/summarizer from the
    # ApplicationContext. process() only needs these collaborators.
    processor = object.__new__(VectorizationProcessor)
    processor.vector_store = store
    processor.kpi = kpi
    processor.embedder = object()

    class _Context:
        def is_summary_generation_enabled(self) -> bool:
            return False

    class _Splitter:
        def split(self, document: Document) -> list[Document]:
            return [Document(page_content="chunk one", metadata={})]

    processor.context = _Context()
    processor.splitter = _Splitter()
    return processor


def test_cancelled_indexing_deletes_partial_vectors_and_propagates_unwrapped(tmp_path, monkeypatch) -> None:
    file_path = tmp_path / "output.md"
    file_path.write_text("some content")

    store = _CancelledVectorStore()
    kpi = _RecordingKpi()
    processor = _processor(store, kpi)

    monkeypatch.setattr(vp_module, "load_langchain_doc_from_metadata", lambda path, md: Document(page_content="full doc", metadata={}))
    monkeypatch.setattr(vp_module, "load_pptx_slide_assets", lambda path: {})

    metadata = _metadata()
    # WorkCancelled must escape unwrapped: upstream tells cancels apart from
    # failures by type, and VectorProcessingError would log as a failure.
    with pytest.raises(WorkCancelled):
        processor.process(str(file_path), metadata)

    assert store.deleted == [metadata.document_uid]
    assert kpi.calls == []
