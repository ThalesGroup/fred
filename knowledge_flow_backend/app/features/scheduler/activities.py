import logging
import pathlib
import tempfile
from app.common.document_structures import DocumentMetadata

from app.features.scheduler.structure import FileToProcess
from temporalio import activity

logger = logging.getLogger(__name__)

def prepare_working_dir(document_uid: str) -> pathlib.Path:
        base = pathlib.Path(tempfile.mkdtemp(prefix=f"doc-{document_uid}-"))
        base.mkdir(parents=True, exist_ok=True)
        (base / "input").mkdir(exist_ok=True)
        (base / "output").mkdir(exist_ok=True)
        return base

@activity.defn
def extract_metadata_activity(file: FileToProcess) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[extract_metadata] Starting for: {file}")
    from app.features.ingestion.service import IngestionService

    ingestion_service = IngestionService()
    if file.is_push():
         logger.info(f"[extract_metadata] push file UID: {file.document_uid}.")
         metadata = ingestion_service.get_metadata(file.document_uid)
         if metadata is None:
             logger.error(f"[extract_metadata] Metadata not found for push file UID: {file.document_uid}")
             raise RuntimeError(f"Metadata missing for push file: {file.document_uid}")

         logger.info(f"[extract_metadata] Metadata found for push file UID: {file.document_uid}, skipping extraction.")
         return metadata
        
    elif file.is_pull():
        raise RuntimeError(f"Not implemented yet: {file.document_uid}")
    
    raise ValueError(f"[extract_metadata] Unknown file type for UID: {file.document_uid}")

@activity.defn
def process_document_activity(file: FileToProcess, metadata: DocumentMetadata) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[process_document] Starting for UID: {metadata.document_uid}")

    from app.features.ingestion.service import IngestionService
    
    ingestion_service = IngestionService()
    working_dir = prepare_working_dir(metadata.document_uid)
    
    if file.is_push():

        # 🗂️ Download input file
        ingestion_service.get_local_copy(metadata, working_dir)
        input_dir = working_dir / "input"
        output_dir = working_dir / "output"
        input_file = next(input_dir.glob("*"))

        # 🧠 Process the file
        ingestion_service.process_input(input_file, output_dir, metadata)

        ingestion_service.save_output(metadata=metadata, output_dir=output_dir)

        ingestion_service.save_metadata(metadata=metadata)
        # Actual processing logic using file and metadata
        logger.info(f"[process_document] Done for UID: {metadata.document_uid}")
        return metadata
    else:
        raise RuntimeError(f"Not implemented yet: {file.document_uid}")

@activity.defn
def vectorize_activity(file: FileToProcess, metadata: DocumentMetadata):
    logger.info(f"[vectorize_and_save] Starting for UID: {metadata.document_uid}")
    from app.features.ingestion.service import IngestionService
    
    working_dir = prepare_working_dir(metadata.document_uid)
    
    ingestion_service = IngestionService()
    if file.is_push():

        # 🧲 Restore document folder from store (input/ and output/)
        ingestion_service.get_local_copy(metadata, working_dir)
        output_dir = working_dir / "output"

        # 📄 Get preview filename (e.g., output.md or table.csv)
        input_file_name = ingestion_service.get_preview_file(metadata, output_dir)

        # 🧠 Process the file
        ingestion_service.process_output(
            output_dir=output_dir,
            input_file_name=input_file_name,
            input_file_metadata=metadata
        )

        ingestion_service.save_output(metadata=metadata, 
                                      output_dir=output_dir)
        ingestion_service.save_metadata(metadata=metadata)
        logger.info(f"[process_document] Done for UID: {metadata.document_uid}")
        return metadata
    else:
        raise RuntimeError(f"Not implemented yet: {file.document_uid}")

