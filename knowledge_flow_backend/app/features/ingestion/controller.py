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
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, KPIActor, KPIWriter, get_current_user
from pydantic import BaseModel

from app.application_context import get_kpi_writer
from app.common.structures import Status
from app.features.ingestion.service import IngestionService
from app.features.scheduler.activities import input_process, output_process
from app.features.scheduler.structure import FileToProcess

logger = logging.getLogger(__name__)


class IngestionInput(BaseModel):
    tags: List[str] = []
    source_tag: str = "fred"


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

    def __init__(self, content, success_count: int, total_count: int, **kwargs):
        # Set status_code based on success_count before calling super().__init__
        status_code = 200 if success_count == total_count else 422
        super().__init__(content, status_code=status_code, **kwargs)
        self.success_count = success_count
        self.total_count = total_count


def uploadfile_to_path(file: UploadFile) -> pathlib.Path:
    tmp_dir = tempfile.mkdtemp()
    filename = file.filename if file.filename is not None else "uploaded_file"
    tmp_path = pathlib.Path(tmp_dir) / filename
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
    Controller for handling ingestion-related operations.
    This controller provides endpoints for uploading and processing documents.
    """

    def __init__(self, router: APIRouter):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.service = IngestionService()
        logger.info("IngestionController initialized.")

        @router.post(
            "/upload-documents",
            tags=["Processing"],
            summary="Upload documents only — defer processing to backend (e.g., Temporal)",
        )
        def upload_documents_sync(
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
            _: KeycloakUser = Depends(get_current_user),
        ) -> Response:
            parsed_input = IngestionInput(**json.loads(metadata_json))
            tags = parsed_input.tags
            source_tag = parsed_input.source_tag

            preloaded_files = []
            for file in files:
                raw_path = uploadfile_to_path(file)
                input_temp_file = save_file_to_temp(raw_path)
                logger.info(f"File {file.filename} saved to temp storage at {input_temp_file}")
                preloaded_files.append((file.filename, input_temp_file))

            total = len(preloaded_files)
            success = 0
            events = []

            for filename, input_temp_file in preloaded_files:
                current_step = "metadata extraction"
                try:
                    output_temp_dir = input_temp_file.parent.parent
                    metadata = self.service.extract_metadata(file_path=input_temp_file, tags=tags, source_tag=source_tag)
                    logger.info(f"Metadata extracted for {filename}: {metadata}")
                    events.append(ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n")

                    current_step = "raw content saving"
                    self.service.save_input(metadata=metadata, input_dir=output_temp_dir / "input")
                    events.append(ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n")

                    current_step = "metadata saving"
                    self.service.save_metadata(metadata=metadata)
                    success += 1

                except Exception as e:
                    logger.exception(f"Failed to process {filename}")
                    error_message = f"{type(e).__name__}: {str(e).strip() or 'No error message'}"
                    events.append(ProcessingProgress(step=current_step, status=Status.ERROR, error=error_message, filename=filename).model_dump_json() + "\n")

            overall_status = Status.SUCCESS if success == total else Status.ERROR
            events.append(json.dumps({"step": "done", "status": overall_status}) + "\n")
            return Response("".join(events), status_code=(200 if success == total else 422), media_type="application/x-ndjson")

        @router.post(
            "/upload-process-documents",
            tags=["Processing"],
            summary="Upload and process documents immediately (end-to-end)",
            description="Ingest and process one or more documents synchronously in a single step.",
        )
        def process_documents_sync(
            files: List[UploadFile] = File(...),
            metadata_json: str = Form(...),
            user: KeycloakUser = Depends(get_current_user),
            kpi: KPIWriter = Depends(get_kpi_writer),
        ) -> Response:
            # Start a timer for the whole call (actor=user). We’ll set final status at the end.
            with kpi.timer(
                "api.request_latency_ms",
                dims={"route": "/upload-process-documents", "method": "POST"},
                actor=KPIActor(type="human", user_id=user.uid),
            ) as t:
                parsed_input = IngestionInput(**json.loads(metadata_json))
                tags = parsed_input.tags
                source_tag = parsed_input.source_tag

                preloaded_files = []
                for file in files:
                    raw_path = uploadfile_to_path(file)
                    input_temp_file = save_file_to_temp(raw_path)
                    logger.info(f"File {file.filename} saved to temp storage at {input_temp_file}")
                    preloaded_files.append((file.filename, input_temp_file))

                total = len(preloaded_files)
                success = 0
                events = []

                for filename, input_temp_file in preloaded_files:
                    current_step = "metadata extraction"
                    try:
                        output_temp_dir = input_temp_file.parent.parent
                        metadata = self.service.extract_metadata(file_path=input_temp_file, tags=tags, source_tag=source_tag)

                        current_step = "input content saving"
                        self.service.save_input(metadata, output_temp_dir / "input")
                        events.append(ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n")

                        current_step = "input processing"
                        metadata = input_process(input_file=input_temp_file, metadata=metadata)
                        events.append(ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n")

                        current_step = "output processing"
                        file_to_process = FileToProcess(
                            document_uid=metadata.document_uid,
                            external_path=None,
                            source_tag=source_tag,
                            tags=tags,
                        )
                        metadata = output_process(file=file_to_process, metadata=metadata, accept_memory_storage=True)
                        events.append(ProcessingProgress(step=current_step, status=Status.SUCCESS, document_uid=metadata.document_uid, filename=filename).model_dump_json() + "\n")

                        current_step = "metadata saving (done)"
                        success += 1

                    except Exception as e:
                        logger.exception(f"Failed to process {filename}")
                        error_message = f"{type(e).__name__}: {str(e).strip() or 'No error message'}"
                        events.append(ProcessingProgress(step=current_step, status=Status.ERROR, error=error_message, filename=filename).model_dump_json() + "\n")

                # override timer status based on outcome (no exception at top-level)
                t.dims["status"] = "ok" if success == total else "error"

                # (Optional) if you have a clear scope for the whole call, add it here:
                # t.dims["scope_type"] = "library"
                # t.dims["scope_id"] = source_tag

                overall_status = Status.SUCCESS if success == total else Status.ERROR
                events.append(json.dumps({"step": "done", "status": overall_status}) + "\n")
                return Response(
                    "".join(events),
                    status_code=(200 if success == total else 422),
                    media_type="application/x-ndjson",
                )
