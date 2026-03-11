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

import asyncio
from datetime import datetime, timezone

import pytest
from fred_core import SQLTableStore, StoreInfo
from langchain_core.documents import Document

from knowledge_flow_backend.common.asyncio_loop_context import asyncio_loop_scope
from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from knowledge_flow_backend.core.processors.output.tabular_processor import tabular_processor as tabular_processor_module
from knowledge_flow_backend.core.processors.output.tabular_processor.tabular_processor import (
    TabularProcessor,
)
from knowledge_flow_backend.features.tabular.registry_service import (
    TabularRegistryService,
    build_physical_table_name,
)


def _metadata(document_uid: str, document_name: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(
            document_uid=document_uid,
            document_name=document_name,
            canonical_name=document_name,
            created=datetime.now(timezone.utc),
        ),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.CSV, row_count=2),
        tags=Tagging(tag_ids=["tag-a"]),
        processing=Processing(stages={ProcessingStage.SQL_INDEXED: ProcessingStatus.NOT_STARTED}),
    )


def _build_processor(monkeypatch, metadata_store, app_context, tmp_path) -> tuple[TabularProcessor, SQLTableStore]:
    tabular_db = tmp_path / "tabular.sqlite"
    store = SQLTableStore(driver="sqlite", path=tabular_db)
    stores_info = {"tabular": StoreInfo(store=store, mode="read_and_write")}

    monkeypatch.setattr(app_context, "get_csv_input_store_info", lambda: ("tabular", store))
    processor = TabularProcessor()
    processor.registry_service = TabularRegistryService(
        registry_store=app_context.get_tabular_dataset_registry_store(),
        stores_info=stores_info,
        metadata_store=metadata_store,
    )

    monkeypatch.setattr(
        tabular_processor_module,
        "load_langchain_doc_from_metadata",
        lambda *_args, **_kwargs: Document(page_content="id,event_date\n1,2024-01-01\n2,2024-01-02\n"),
    )
    return processor, store


def test_tabular_processor_saves_physical_table_and_registry(monkeypatch, tmp_path, metadata_store, app_context):
    metadata = _metadata("doc-csv-processor", "sales.csv")
    processor, store = _build_processor(monkeypatch, metadata_store, app_context, tmp_path)
    processed = processor.process(str(tmp_path / "sales.csv"), metadata)
    physical_table_name = build_physical_table_name(metadata.document_uid)
    dataset = asyncio.run(processor.registry_service.get_by_document_uid(metadata.document_uid))

    assert processed.processing.stages[ProcessingStage.SQL_INDEXED] == ProcessingStatus.DONE
    assert physical_table_name in set(store.list_tables())
    assert dataset is not None
    assert dataset.db_name == "tabular"
    assert dataset.physical_table_name == physical_table_name
    assert dataset.row_count == 2


@pytest.mark.asyncio
async def test_tabular_processor_upserts_registry_from_worker_thread(monkeypatch, tmp_path, metadata_store, app_context):
    metadata = _metadata("doc-csv-threaded", "sales.csv")
    processor, store = _build_processor(monkeypatch, metadata_store, app_context, tmp_path)

    with asyncio_loop_scope(asyncio.get_running_loop()):
        processed = await asyncio.to_thread(processor.process, str(tmp_path / "sales.csv"), metadata)

    physical_table_name = build_physical_table_name(metadata.document_uid)
    dataset = await processor.registry_service.get_by_document_uid(metadata.document_uid)

    assert processed.processing.stages[ProcessingStage.SQL_INDEXED] == ProcessingStatus.DONE
    assert physical_table_name in set(store.list_tables())
    assert dataset is not None
    assert dataset.physical_table_name == physical_table_name
    assert dataset.row_count == 2
