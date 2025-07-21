import logging
from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.features.scheduler.structure import FileToProcess
from temporalio import activity

logger = logging.getLogger(__name__)

@activity.defn
def extract_metadata_activity(file: FileToProcess) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[extract_metadata] Starting for: {file}")
    from app.application_context import ApplicationContext
    
    if file.is_push():
         logger.info(f"[extract_metadata] push file UID: {file.document_uid}.")
         metadata_store = ApplicationContext.get_instance().get_metadata_store()
         metadata = metadata_store.get_metadata_by_uid(file.document_uid)
         if metadata is None:
             logger.error(f"[extract_metadata] Metadata not found for push file UID: {file.document_uid}")
             raise RuntimeError(f"Metadata missing for push file: {file.document_uid}")

         logger.info(f"[extract_metadata] Metadata found for push file UID: {file.document_uid}, skipping extraction.")
         return metadata
        
    elif file.is_pull():
        content_store = ApplicationContext.get_instance().get_content_store()
        file_path = content_store.get_local_copy(file.document_uid)
        logger.info(f"[extract_metadata] Pulled file available at: {file_path}")
        raise RuntimeError(f"Not implemented yet: {file.document_uid}")
    
    raise ValueError(f"[extract_metadata] Unknown file type for UID: {file.document_uid}")

@activity.defn
def process_document_activity(file: FileToProcess, metadata: DocumentMetadata):
    logger = activity.logger
    logger.info(f"[process_document] Starting for UID: {metadata.document_uid}")
    metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
    from app.application_context import ApplicationContext
    metadata_store = ApplicationContext.get_instance().get_metadata_store()
    metadata_store.save_metadata(metadata=metadata)
    # Actual processing logic using file and metadata
    logger.info(f"[process_document] Done for UID: {metadata.document_uid}")

@activity.defn
def vectorize_activity(file: FileToProcess, metadata: DocumentMetadata):
    logger.info(f"[vectorize_and_save] Starting for UID: {metadata.document_uid}")
    metadata.mark_stage_done(ProcessingStage.VECTORIZED)
    from app.application_context import ApplicationContext
    metadata_store = ApplicationContext.get_instance().get_metadata_store()
    metadata_store.save_metadata(metadata=metadata)
    logger.info(f"[vectorize_and_save] Completed for UID: {metadata.document_uid}")
