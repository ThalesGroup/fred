import logging
import pathlib
import tempfile
from app.common.document_structures import DocumentMetadata


from app.features.scheduler.structure import FileToProcess
from temporalio import activity
from temporalio import exceptions

logger = logging.getLogger(__name__)


def prepare_working_dir(document_uid: str) -> pathlib.Path:
    base = pathlib.Path(tempfile.mkdtemp(prefix=f"doc-{document_uid}-"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "input").mkdir(exist_ok=True)
    (base / "output").mkdir(exist_ok=True)
    return base


@activity.defn
def extract_metadata(file: FileToProcess) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[extract_metadata] Starting for: {file}")
    from app.features.ingestion.service import IngestionService

    ingestion_service = IngestionService()
    if file.is_push():
        logger.info(f"[extract_metadata] push file UID: {file.document_uid}.")
        assert file.document_uid, "Push files must have a document UID"
        metadata = ingestion_service.get_metadata(file.document_uid)
        if metadata is None:
            logger.error(f"[extract_metadata] Metadata not found for push file UID: {file.document_uid}")
            raise RuntimeError(f"Metadata missing for push file: {file.document_uid}")

        logger.info(f"[extract_metadata] Metadata found for push file UID: {file.document_uid}, skipping extraction.")
        return metadata

    else:
        from app.common.source_utils import get_pull_base_path

        # Step 1: Resolve full path
        base_path = get_pull_base_path(file.source_tag)
        assert file.external_path, "Pull files must have an external path"
        assert base_path, "Base path for pull files must be defined"
        full_path = base_path / file.external_path

        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"Pull file not found at: {full_path}")

        logger.info(f"[extract_metadata] Found file at: {full_path}")

        # Step 2: Extract metadata using input processor
        metadata = ingestion_service.extract_metadata(full_path, tags=file.tags, source_tag=file.source_tag)
        logger.info(f"[extract_metadata] generated : {metadata}")

        # Step 4: Save metadata
        ingestion_service.save_metadata(metadata=metadata)

        logger.info(f"[extract_metadata] Metadata extracted and saved for pull file: {metadata.document_uid}")
        return metadata


@activity.defn
def input_process(file: FileToProcess, metadata: DocumentMetadata) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[process_document] Starting for UID: {metadata.document_uid}")

    from app.features.ingestion.service import IngestionService

    ingestion_service = IngestionService()
    working_dir = prepare_working_dir(metadata.document_uid)
    input_dir = working_dir / "input"
    output_dir = working_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    if file.is_push():
        # 🗂️ Download input file
        ingestion_service.get_local_copy(metadata, working_dir)
        input_file = next(input_dir.glob("*"))
    else:
        from app.common.source_utils import get_pull_base_path
        assert file.external_path, "Pull files must have an external path"
        logger.info(f"[process_document] Resolving pull file: source_tag={file.source_tag}, path={file.external_path}")
        full_path = get_pull_base_path(file.source_tag) / file.external_path

        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"Pull file not found: {full_path}")

        # 🗂️ Copy file into working directory
        target_path = input_dir / full_path.name
        target_path.write_bytes(full_path.read_bytes())
        input_file = target_path

    # 🧠 Process the file
    ingestion_service.process_input(input_file, output_dir, metadata)

    ingestion_service.save_output(metadata=metadata, output_dir=output_dir)

    ingestion_service.save_metadata(metadata=metadata)
    # Actual processing logic using file and metadata
    logger.info(f"[process_document] Done for UID: {metadata.document_uid}")
    return metadata


@activity.defn
def output_process(file: FileToProcess, metadata: DocumentMetadata, accept_memory_storage: bool = False) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[vectorize_and_save] Starting for UID: {metadata.document_uid}")

    from app.features.ingestion.service import IngestionService
    from app.application_context import ApplicationContext

    working_dir = prepare_working_dir(metadata.document_uid)
    output_dir = working_dir / "output"
    ingestion_service = IngestionService()

    # ✅ For both push and pull, restore what was saved (input/output)
    ingestion_service.get_local_copy(metadata, working_dir)

    # 📄 Locate preview file
    preview_file = ingestion_service.get_preview_file(metadata, output_dir)

    if not ApplicationContext.get_instance().is_tabular_file(preview_file.name):
        vector_store_type = ApplicationContext.get_instance().get_config().vector_storage.type
        if vector_store_type == "in_memory" and not accept_memory_storage:
            raise exceptions.ApplicationError(
                "❌ Vectorization from temporal activity is not allowed with an in-memory vector store. Please configure a persistent vector store like OpenSearch.",
                non_retryable=True,
            )
    # Proceed with the output processing
    ingestion_service.process_output(output_dir=output_dir, input_file_name=preview_file.name, input_file_metadata=metadata)

    # 💾 Save updated output and metadata
    ingestion_service.save_output(metadata=metadata, output_dir=output_dir)
    ingestion_service.save_metadata(metadata=metadata)

    logger.info(f"[vectorize_and_save] Done for UID: {metadata.document_uid}")
    return metadata

