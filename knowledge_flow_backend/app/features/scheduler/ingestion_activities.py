import logging
from app.features.ingestion.service import IngestionService
from temporalio import activity
from pathlib import Path
from app.application_context import ApplicationContext

logger = logging.getLogger(__name__)

@activity.defn
def extract_metadata(file, base_metadata: dict) -> dict:
    logger.info(f"[extract_metadata] Starting for file: {file.path}")
    service = IngestionService()
    metadata = service.extract_metadata(Path(file.path), base_metadata)
    logger.info(f"[extract_metadata] Done. UID: {metadata.get('document_uid')}")
    return metadata

@activity.defn
def process_document(file, metadata: dict):
    logger.info(f"[process_document] Starting for UID: {metadata.get('document_uid')}")
    input_path = Path(file.path)
    service = IngestionService()
    service.process_input(input_path.parent, input_path, metadata)
    logger.info(f"[process_document] Done for UID: {metadata.get('document_uid')}")

@activity.defn
def vectorize_and_save(file, metadata: dict):
    logger.info(f"[vectorize_and_save] Starting for UID: {metadata.get('document_uid')}")
    input_path = Path(file.path)
    app_context = ApplicationContext.get_instance()
    output_service = IngestionService()
    output_service.process_output(input_path.parent, input_path, metadata)
    app_context.get_metadata_store().save_metadata(metadata)
    ApplicationContext.get_instance().get_content_store().save_content(metadata["document_uid"], input_path.parent)
    logger.info(f"[vectorize_and_save] Completed for UID: {metadata.get('document_uid')}")
