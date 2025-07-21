import logging
from app.features.scheduler.structure import FileToProcess
from temporalio import activity

logger = logging.getLogger(__name__)

# def _extract_metadata(self, file_path: pathlib.Path, 
#                          tags: list[str], 
#                          source_tag: str = "uploads") -> DocumentMetadata:
#         suffix = file_path.suffix.lower()
#         processor = ApplicationContext.get_instance().get_input_processor_instance(suffix)
#         source_config = ApplicationContext.get_instance().get_config().document_sources.get(source_tag)
#         metadata = processor.process_metadata(file_path, tags=tags, source_tag=source_tag)
#         if source_config:
#             metadata.source_type = source_config.type
#         return metadata

@activity.defn
def extract_metadata(file: FileToProcess):
    logger = activity.logger
    logger.info(f"[extract_metadata] Starting for: {file}")

    # Resolve the content file path (assumes file.document_uid points to stored file)
   # content_store = ApplicationContext.get_instance().get_content_store()
    #file_path = content_store.get_local_copy(file.document_uid) 
    # return DocumentMetadata(
    #     document_uid="dummy-uid",
    #     source_tag=file.source_tag,
    #     tags=file.tags,
    #     original_filename="dummy.txt"
    # )
    # Run metadata extraction
    # metadata = _extract_metadata(
    #     file_path=file_path,
    #     tags=file.tags,
    #     source_tag=file.source_tag
    # )

    # logger.info(f"[extract_metadata] Done. UID: {metadata.document_uid}")
    # return metadata

@activity.defn
def process_document(file: FileToProcess, metadata: dict):
    logger.info(f"[process_document] Starting for UID: {metadata.get('document_uid')}")
    logger.info(f"[process_document] Done for UID: {metadata.get('document_uid')}")

@activity.defn
def vectorize_and_save(file: FileToProcess, metadata: dict):
    logger.info(f"[vectorize_and_save] Starting for UID: {metadata.get('document_uid')}")
    logger.info(f"[vectorize_and_save] Completed for UID: {metadata.get('document_uid')}")
