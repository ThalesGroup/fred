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
import logging
import pathlib
import tempfile

from fred_core import KeycloakUser
from temporalio import activity

from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


def _first_input_file(input_dir: pathlib.Path) -> pathlib.Path:
    for candidate in input_dir.glob("*"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No input file found in working directory: {input_dir}")


async def resolve_push_input_file_for_worker(
    *,
    user: KeycloakUser,
    metadata: DocumentMetadata,
    working_dir: pathlib.Path,
) -> pathlib.Path:
    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()
    await asyncio.to_thread(ingestion_service.get_local_copy, user, metadata, working_dir)
    return _first_input_file(working_dir / "input")


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
async def push_input_process(
    user: KeycloakUser,
    metadata: DocumentMetadata,
    input_file: str = "",
) -> DocumentMetadata:
    """
    Process push-file input and persist generated output in content storage.
    The input may be provided directly (local fast path) or restored from content
    storage on the current worker.
    """
    logger = activity.logger
    logger.info("[SCHEDULER][ACTIVITY][PUSH_INPUT_PROCESS] Starting uid=%s", metadata.document_uid)

    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()

    try:
        metadata.set_stage_status(ProcessingStage.PREVIEW_READY, ProcessingStatus.IN_PROGRESS)
        await ingestion_service.save_metadata(user, metadata=metadata)

        with tempfile.TemporaryDirectory(prefix=f"doc-{metadata.document_uid}-") as tmpdir:
            working_dir = pathlib.Path(tmpdir)
            input_dir = working_dir / "input"
            output_dir = working_dir / "output"
            input_dir.mkdir(exist_ok=True)
            output_dir.mkdir(exist_ok=True)

            if input_file:
                resolved_input_file = pathlib.Path(input_file)
                if not resolved_input_file.exists() or not resolved_input_file.is_file():
                    raise FileNotFoundError(f"Provided push input file does not exist for document {metadata.document_uid}: {resolved_input_file}")
            else:
                try:
                    resolved_input_file = await resolve_push_input_file_for_worker(
                        user=user,
                        metadata=metadata,
                        working_dir=working_dir,
                    )
                except Exception as exc:
                    raise FileNotFoundError(f"Push input restore failed for document {metadata.document_uid}.") from exc

            await asyncio.to_thread(
                ingestion_service.process_input,
                user,
                resolved_input_file,
                output_dir,
                metadata,
            )
            await asyncio.to_thread(ingestion_service.save_output, user, metadata, output_dir)

        metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
        await ingestion_service.save_metadata(user, metadata=metadata)
        logger.info("[SCHEDULER][ACTIVITY][PUSH_INPUT_PROCESS] completed uid=%s", metadata.document_uid)
        return metadata
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"
        metadata.mark_stage_error(ProcessingStage.PREVIEW_READY, error_message)
        try:
            await ingestion_service.save_metadata(user, metadata=metadata)
        except Exception:
            logger.exception(
                "[SCHEDULER][ACTIVITY][PUSH_INPUT_PROCESS] failed to persist error state uid=%s",
                metadata.document_uid,
                exc_info=True,
            )
        logger.exception(
            "[SCHEDULER][ACTIVITY][PUSH_INPUT_PROCESS] failed uid=%s",
            metadata.document_uid,
            exc_info=True,
        )
        raise
