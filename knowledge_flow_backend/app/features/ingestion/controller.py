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

import json
import logging
import pathlib
import shutil
import tempfile
from typing import Generator, List, Optional
from app.common.structures import Status
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.common.document_structures import ProcessingStage
from app.features.ingestion.service import IngestionService
from app.features.metadata.service import MetadataService

logger = logging.getLogger(__name__)

class IngestionInput(BaseModel):
    tags: List[str] = []
    source_tag: str = "uploads"


class ProcessingProgress(BaseModel):
    """
    Represents the progress of a file processing operation. It is used to report in
    real-time the status of the processing pipeline to the REST remote client.
    Attributes:
        step (str): The current step in the processing pipeline.
        filename (str): The name of the file being processed.
        status (str): The status of the processing operation.
        document_uid (Optional[str]): A unique identifier for the document, if available.
    """

    step: str
    filename: str
    status: Status
    error: Optional[str] = None
    document_uid: Optional[str] = None


class StatusAwareStreamingResponse(StreamingResponse):
    """
    A custom StreamingResponse that allows for setting the HTTP status code
    based on the success of the content processing.
    This is useful for streaming responses where the final status may not be known
    until the generator has completed.
    """

    def __init__(self, content: Generator, all_success_flag: list, **kwargs):
        super().__init__(content, media_type="application/x-ndjson", **kwargs)
        self.all_success_flag = all_success_flag

    async def listen_for_close(self):
        await super().listen_for_close()
        # Set final HTTP status based on content
        if not self.all_success_flag[0]:
            self.status_code = 422  # or 207 if you prefer partial success

def uploadfile_to_path(file: UploadFile) -> pathlib.Path:
    tmp_dir = tempfile.mkdtemp()
    tmp_path = pathlib.Path(tmp_dir) / file.filename
    with open(tmp_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    return tmp_path

def save_file_to_temp(source_file_path: pathlib.Path) -> pathlib.Path:
        """
        Copies the given local file into a new temp folder and returns the new path.
        """
        temp_dir = pathlib.Path(tempfile.mkdtemp()) / "input"
        temp_dir.mkdir(parents=True, exist_ok=True)

        target_path = temp_dir / source_file_path.name
        shutil.copyfile(source_file_path, target_path)
        logger.info(f"File copied to temporary location: {target_path}")
        return target_path
class IngestionController:
    """
    Controller responsible for handling the initial ingestion pipeline.

    Current Responsibilities:
    --------------------------
    This controller manages the **entire ingestion lifecycle** in one endpoint:
    1. Temporary storage of uploaded files
    2. Metadata extraction
    3. Document processing (e.g. chunking)
    4. Vectorization and post-processing
    5. Metadata persistence
    6. Raw content storage

    It emits a streaming NDJSON response (`ProcessingProgress`) for real-time tracking
    of the ingestion steps.

    Design Note:
    ------------
    This controller is deliberately implemented as a **first, monolithic prototype** to
    validate the ingestion workflow end-to-end. While this design is operational and
    suitable for low-concurrency environments, it is **not the final architecture**.

    In a future refactoring, this will likely be split into:
    - `ContentController`: handles file upload, raw content storage, UID assignment
    - `ProcessingController`: triggers the async processing pipeline (chunking, embedding, etc.)

    This separation will:
    - Improve modularity and testability
    - Support ingestion from other sources (e.g., FTP, S3, user portal)
    - Enable processing reuse for re-indexing, multi-agent ingestion, etc.

    For now, developers **should not worry** about this architectural limitation. The current
    implementation is reliable and aligned with the rest of the platform.

    Endpoint:
    ---------
    - POST `/process-files`: main endpoint to upload and process one or more files
      - Accepts a `metadata_json` Form field and multiple files
      - Returns a streaming response of progress events

    Dependencies:
    -------------
    - `IngestionService` for file I/O
    - `InputProcessorService` for metadata & chunking
    - `OutputProcessorService` for post-processing
    - `ContentStore` and `MetadataStore` for persistence
    """

    def __init__(self, router: APIRouter):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.service = IngestionService()
        logger.info("IngestionController initialized.")

        @router.post(
            "/process-files",
            tags=["Library Ingestion"],
            summary="Upload and process documents immediately (end-to-end)",
            description="""
        This endpoint handles the **full ingestion pipeline in one step**, ideal for local development, demo environments, or smaller-scale backends.

        ### Responsibilities:
        - Saves uploaded files to temporary storage
        - Extracts document metadata
        - Processes the document (e.g., parsing, chunking, embedding)
        - Saves content to persistent storage
        - Persists metadata and indexing info

        ### Response Format:
        A **streaming NDJSON response** containing `ProcessingProgress` updates for each step of each file. The client receives real-time feedback.

        ### When to use:
        - Development or laptop-based deployments
        - Manual ingestion workflows
        - Small file batches with real-time feedback

        **Not recommended for high-volume ingestion** due to synchronous, blocking behavior.
        """
        )
        def stream_process(
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
        ) -> StreamingResponse:
            parsed_input = IngestionInput(**json.loads(metadata_json))
            tags = parsed_input.tags
            source_tag = parsed_input.source_tag
            #input_metadata = json.loads(metadata_json)
            # ✅ Preload: Call save_file_to_temp on all files before the generator runs
            # This is to ensure that the files are saved to temp storage before processing
            # and to avoid blocking the generator with file I/O operations.
            preloaded_files = []
            for file in files:
                raw_path = uploadfile_to_path(file)
                input_temp_file = save_file_to_temp(raw_path)
                logger.info(f"File {file.filename} saved to temp storage at {input_temp_file}")
                preloaded_files.append((file.filename, input_temp_file))
            all_success_flag = [False]  # Track success across all files

            def event_generator() -> Generator[str, None, None]:
                for filename, input_temp_file in preloaded_files:
                    current_step = "metadata extraction"

                    try:
                        output_temp_dir = input_temp_file.parent.parent

                        # Step: Metadata extraction
                        metadata = self.service.extract_metadata(input_temp_file, tags=tags, source_tag=source_tag)
                        logger.info(f"Metadata extracted for {filename}: {metadata}")
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                        if self.service.get_metadata(metadata.document_uid):
                            logger.error(f"Metadata already exists for {filename}: {metadata}")

                        # Step: Processing
                        current_step = "document knowledge extraction"
                        self.service.process_input(
                            input_path=input_temp_file,
                            output_dir=output_temp_dir / "output",
                            metadata=metadata
                        )
                        logger.info(f"Document processed for {filename}: {metadata}")
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                        # Step: Post-processing (optional)
                        current_step = "knowledge post processing"
                        metadata.mark_stage_done(ProcessingStage.VECTORIZED)
                        vectorization_response = self.service.process_output(
                            output_dir=output_temp_dir / "output",
                            input_file_name=input_temp_file.name,
                            input_file_metadata=metadata
                        )
                        logger.info(f"Post-processing completed for {filename}: {metadata}")
                        yield ProcessingProgress(step=current_step,
                                                 status=vectorization_response.status,
                                                 document_uid=metadata.document_uid,
                                                 filename=filename).model_dump_json() + "\n"

                        # Step: Uploading to backend storage
                        current_step = "raw content saving"
                        self.service.save_input(metadata, output_temp_dir / "input")
                        self.service.save_output(metadata, output_temp_dir / "output")
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS,
                                                 document_uid=metadata.document_uid,
                                                 filename=filename).model_dump_json() + "\n"
                        # Step: Metadata saving
                        current_step = "metadata saving"
                        self.service.save_metadata(metadata)
                        logger.info(f"Metadata saved for {filename}: {metadata}")
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS,
                                                 document_uid=metadata.document_uid,
                                                 filename=filename).model_dump_json() + "\n"

                        # ✅ At least one file succeeded
                        all_success_flag[0] = True
                    except Exception as e:
                        logger.exception(f"Failed to process {file.filename}")
                        # Send detailed error message (safe for frontend)
                        error_message = f"{type(e).__name__}: {str(e).strip() or 'No error message'}"
                        yield ProcessingProgress(step=current_step,
                                                 status=Status.ERROR, error=error_message,
                                                 filename=file.filename).model_dump_json() + "\n"
                yield json.dumps({"step": "done", "status": Status.SUCCESS if all_success_flag[0] else "error"}) + "\n"

            return StatusAwareStreamingResponse(event_generator(), all_success_flag=all_success_flag)


        @router.post(
            "/upload-files",
            tags=["Library Ingestion"],
            summary="Upload documents only — defer processing to backend (e.g., Temporal)",
            description="""
        This endpoint allows **fast, lightweight upload of one or more documents** to temporary storage, with metadata extraction.

        It **does not** perform any heavy processing (e.g., vectorization, chunking, indexing). Instead, the uploaded files are stored and **ready for deferred processing** via an asynchronous pipeline (e.g., Temporal workflows).

        ### Responsibilities:
        - Saves uploaded files to temporary storage
        - Extracts metadata and persists it
        - Stores the original content

        ### Response Format:
        A **streaming NDJSON response** with `ProcessingProgress` events, limited to:
        - Metadata extraction
        - Metadata persistence
        - Raw content saving

        ### When to use:
        - Large-scale ingestion jobs
        - Asynchronous architectures (e.g., Temporal worker queues)
        - Background or batch ingestion pipelines

        Use this endpoint to separate **I/O-bound upload** from **compute-heavy processing**.
        """
        )
        def stream_load(
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
        ) -> StreamingResponse:
            parsed_input = IngestionInput(**json.loads(metadata_json))
            tags = parsed_input.tags
            source_tag = parsed_input.source_tag
            # ✅ Preload: Call save_file_to_temp on all files before the generator runs
            # This is to ensure that the files are saved to temp storage before processing
            # and to avoid blocking the generator with file I/O operations.
            preloaded_files = []
            for file in files:
                raw_path = uploadfile_to_path(file)
                input_temp_file = save_file_to_temp(raw_path)
                logger.info(f"File {file.filename} saved to temp storage at {input_temp_file}")
                preloaded_files.append((file.filename, input_temp_file))
            all_success_flag = [False]  # Track success across all files

            def event_generator() -> Generator[str, None, None]:
                for filename, input_temp_file in preloaded_files:
                    current_step = "metadata extraction"

                    try:
                        output_temp_dir = input_temp_file.parent.parent

                        # Step: Metadata extraction
                        metadata = self.service.extract_metadata(
                            file_path=input_temp_file, tags=tags, source_tag=source_tag)
                        logger.info(f"Metadata extracted for {filename}: {metadata}")
                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"

                        # check if metadata is already known if so delete it to replace it and process the
                        # document again
                        if self.service.get_metadata(metadata.document_uid):
                            logger.error(f"Metadata already exists for {filename}: {metadata}")

                        yield ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n"
                        # Step: Uploading to backend storage
                        current_step = "raw content saving"
                        self.service.save_input(metadata=metadata, input_dir=output_temp_dir / "input")
                        yield ProcessingProgress(step=current_step,
                                                 status=Status.SUCCESS,
                                                 document_uid=metadata.document_uid,
                                                 filename=filename).model_dump_json() + "\n"
                        # ✅ At least one file succeeded
                        # Step 2: Metadata saving
                        current_step = "metadata saving"
                        self.service.save_metadata(metadata=metadata)
                        logger.info(f"Metadata saved for {filename}: {metadata}")
                        all_success_flag[0] = True
                    except Exception as e:
                        logger.exception(f"Failed to process {file.filename}")
                        # Send detailed error message (safe for frontend)
                        error_message = f"{type(e).__name__}: {str(e).strip() or 'No error message'}"
                        yield ProcessingProgress(step=current_step, status=Status.ERROR, error=error_message, filename=file.filename).model_dump_json() + "\n"
                yield json.dumps({"step": "done", "status": Status.SUCCESS if all_success_flag[0] else "error"}) + "\n"

            return StatusAwareStreamingResponse(event_generator(), all_success_flag=all_success_flag)
