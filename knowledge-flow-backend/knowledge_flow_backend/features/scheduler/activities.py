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

import logging
import pathlib
import tempfile

from fred_core import KeycloakUser
from temporalio import activity, exceptions

from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


def prepare_working_dir(document_uid: str) -> pathlib.Path:
    base = pathlib.Path(tempfile.mkdtemp(prefix=f"doc-{document_uid}-"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "input").mkdir(exist_ok=True)
    (base / "output").mkdir(exist_ok=True)
    return base


@activity.defn
async def create_pull_file_metadata(file: FileToProcess) -> DocumentMetadata:
    assert file.external_path, "Pull files must have an external path"
    assert file.source_tag, "Pull files must have a source tag"
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][CREATE_PULL_FILE_METADATA] Starting file={file}")
    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()

    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    loader = context.get_content_loader(file.source_tag)

    # Step 2: Fetch local file path from loader (downloads if needed)
    with tempfile.TemporaryDirectory() as tmpdir:
        destination = pathlib.Path(tmpdir)
        full_path = loader.fetch_by_relative_path(file.external_path, destination)

        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"Pull file not found after fetch: {full_path}")

        logger.info(f"[SCHEDULER][ACTIVITY][CREATE_PULL_FILE_METADATA] Fetched file path={full_path}")

        # Step 3: Extract and save metadata
        ingestion_service = IngestionService()
        metadata = await ingestion_service.extract_metadata(file.processed_by, full_path, tags=file.tags, source_tag=file.source_tag)
        metadata.source.pull_location = file.external_path
        logger.info(f"[SCHEDULER][ACTIVITY][CREATE_PULL_FILE_METADATA] metadata={metadata}")

        await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

        logger.info(f"[SCHEDULER][ACTIVITY][CREATE_PULL_FILE_METADATA] Metadata extracted and saved uid={metadata.document_uid}")
        return metadata


@activity.defn
async def get_push_file_metadata(file: FileToProcess) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] Starting file={file}")
    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()
    logger.info(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] push file uid={file.document_uid}.")
    assert file.document_uid, "Push files must have a document UID"
    metadata = await ingestion_service.get_metadata(file.processed_by, file.document_uid)
    if metadata is None:
        logger.error(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] Metadata not found uid={file.document_uid}")
        raise RuntimeError(f"Metadata missing for push file: {file.document_uid}")

    logger.info(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] Metadata found for push file skipping extraction uid={file.document_uid}")
    return metadata


@activity.defn
async def load_push_file(file: FileToProcess, metadata: DocumentMetadata) -> str:
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][LOAD_PUSH_FILE] Loading file uid={metadata.document_uid}")

    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()
    working_dir = prepare_working_dir(metadata.document_uid)
    input_dir = working_dir / "input"
    output_dir = working_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    # 🗂️ Download input file
    ingestion_service.get_local_copy(file.processed_by, metadata, working_dir)
    input_file = next(input_dir.glob("*"))
    # Temporal payloads must be JSON-serializable.
    return str(input_file)


@activity.defn
async def load_pull_file(file: FileToProcess, metadata: DocumentMetadata) -> str:
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][LOAD_PULL_FILE] Fetching file uid={metadata.document_uid}")

    assert metadata.source_tag, "Missing source_tag in metadata"
    assert metadata.pull_location, "Missing pull_location in metadata"

    working_dir = prepare_working_dir(metadata.document_uid)
    input_dir = working_dir / "input"
    output_dir = working_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    from knowledge_flow_backend.application_context import ApplicationContext

    loader = ApplicationContext.get_instance().get_content_loader(metadata.source_tag)
    full_path = loader.fetch_by_relative_path(metadata.pull_location, input_dir)

    if not full_path.exists() or not full_path.is_file():
        raise FileNotFoundError(f"File not found after fetch: {full_path}")

    logger.info(f"[SCHEDULER][ACTIVITY][LOAD_PULL_FILE] File copied to working dir: path={full_path}")
    # Temporal payloads must be JSON-serializable.
    return str(full_path)


@activity.defn
async def input_process(user: KeycloakUser, input_file: str, metadata: DocumentMetadata) -> DocumentMetadata:
    """
    Processes the provided local input file and saves the metadata.
    This method generates the output files (preview, markdown, CSV) and
    invokes the ingestion service to save all that to the content store.
    """
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][INPUT_PROCESS] Starting uid={metadata.document_uid}")

    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()
    working_dir = prepare_working_dir(metadata.document_uid)
    input_dir = working_dir / "input"
    output_dir = working_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    # Process the file
    ingestion_service.process_input(user, pathlib.Path(input_file), output_dir, metadata)
    ingestion_service.save_output(user, metadata=metadata, output_dir=output_dir)

    metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
    await ingestion_service.save_metadata(user, metadata=metadata)

    logger.info(f"[SCHEDULER][ACTIVITY][INPUT_PROCESS] completed uid={metadata.document_uid}")
    return metadata


@activity.defn
async def output_process(file: FileToProcess, metadata: DocumentMetadata, accept_memory_storage: bool = False) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] Starting uid={metadata.document_uid}")

    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    working_dir = prepare_working_dir(metadata.document_uid)
    output_dir = working_dir / "output"
    ingestion_service = IngestionService()

    # ✅ For both push and pull, restore what was saved (input/output)
    ingestion_service.get_local_copy(file.processed_by, metadata, working_dir)

    # 📄 Locate preview file
    preview_file = ingestion_service.get_preview_file(file.processed_by, metadata, output_dir)

    if not ApplicationContext.get_instance().is_tabular_file(preview_file.name):
        from knowledge_flow_backend.common.structures import InMemoryVectorStorage

        vector_store = ApplicationContext.get_instance().get_config().storage.vector_store
        if isinstance(vector_store, InMemoryVectorStorage) and not accept_memory_storage:
            raise exceptions.ApplicationError(
                "❌ Vectorization from temporal activity is not allowed with an in-memory vector store. Please configure a persistent vector store like OpenSearch.",
                non_retryable=True,
            )
    # Proceed with the output processing
    metadata = ingestion_service.process_output(file.processed_by, output_dir=output_dir, input_file_name=preview_file.name, input_file_metadata=metadata)

    # Save the updated metadata
    await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

    logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] completed uid={metadata.document_uid}")
    return metadata


@activity.defn
async def fast_store_vectors(payload: dict) -> dict:
    """
    Store fast-ingest chunks into the configured vector store.
    Payload shape:
      {
        "documents": [{"page_content": str, "metadata": dict}, ...]
      }
    """
    logger = activity.logger
    docs_payload = payload.get("documents") or []
    if not isinstance(docs_payload, list):
        raise ValueError("payload.documents must be a list")

    from langchain_core.documents import Document

    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    embedder = context.get_embedder()
    vector_store = context.get_create_vector_store(embedder)

    docs = []
    for item in docs_payload:
        if not isinstance(item, dict):
            continue
        page_content = str(item.get("page_content") or "")
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        docs.append(Document(page_content=page_content, metadata=metadata))

    if not docs:
        return {"chunks": 0}

    ids = vector_store.add_documents(docs)
    chunks = len(ids) if isinstance(ids, (list, tuple, set)) else len(docs)
    logger.info("[SCHEDULER][ACTIVITY][FAST_STORE_VECTORS] Stored %d chunks", chunks)
    return {"chunks": chunks}


@activity.defn
async def fast_delete_vectors(payload: dict) -> dict:
    """
    Delete all vectors for a fast-ingested document.
    Payload: {"document_uid": "<uid>"}
    """
    document_uid = payload.get("document_uid")
    if not document_uid:
        raise ValueError("payload.document_uid is required")

    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    embedder = context.get_embedder()
    vector_store = context.get_create_vector_store(embedder)
    vector_store.delete_vectors_for_document(document_uid=document_uid)
    activity.logger.info("[SCHEDULER][ACTIVITY][FAST_DELETE_VECTORS] Deleted vectors for %s", document_uid)
    return {"status": "ok", "document_uid": document_uid}
