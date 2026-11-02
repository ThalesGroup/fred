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
from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from temporalio import activity

from knowledge_flow_worker.common.processing_profile_context import coerce_processing_profile
from knowledge_flow_worker.common.structures import IngestionProcessingProfile
from knowledge_flow_worker.features.manager_processing.client import raise_permanent_failure
from knowledge_flow_worker.features.manager_processing.service import manager_service
from knowledge_flow_worker.features.scheduler.activity_utils import await_with_heartbeat, raise_if_document_deleted, to_thread_with_heartbeat
from knowledge_flow_worker.features.scheduler.extraction_process import extract_document
from knowledge_flow_worker.features.scheduler.kpi_utils import emit_temporal_activity_queue_wait_kpi, emit_temporal_activity_result_kpis
from knowledge_flow_worker.features.scheduler.logging_context import ingestion_activity
from knowledge_flow_worker.features.scheduler.scheduler_structures import FileToProcess

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
    ingestion_service,
) -> pathlib.Path:
    await asyncio.to_thread(ingestion_service.get_local_copy, user, metadata, working_dir)
    return _first_input_file(working_dir / "input")


@activity.defn
@ingestion_activity
async def get_push_file_metadata(file: FileToProcess) -> DocumentMetadata:
    """
    Why:
    This is the first push-document activity and therefore captures queue wait
    before the ingestion pipeline starts processing document content.

    How:
    Emit the Temporal queue-wait KPI, then load metadata for the push document.
    """
    logger = activity.logger
    started_at = asyncio.get_running_loop().time()
    logger.info("Push metadata activity started")
    emit_temporal_activity_queue_wait_kpi(phase="metadata")

    ingestion_service = await manager_service(file.source_tag, "preparation", file=file)
    logger.info(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] push file uid={file.document_uid}.")
    assert file.document_uid, "Push files must have a document UID"
    metadata = await ingestion_service.get_metadata(file.processed_by, file.document_uid)
    if metadata is None:
        logger.error(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] Metadata not found uid={file.document_uid}")
        raise RuntimeError(f"Metadata missing for push file: {file.document_uid}")

    metadata.processing.profile = file.profile
    raise_if_document_deleted(await ingestion_service.persist_progress(file.processed_by, metadata=metadata), metadata.document_uid)

    logger.info(f"[SCHEDULER][ACTIVITY][GET_PUSH_FILE_METADATA] Metadata found for push file skipping extraction uid={file.document_uid}")
    emit_temporal_activity_result_kpis(
        phase="metadata",
        started_at_monotonic=started_at,
        metadata=metadata,
        file=file,
        status="success",
    )
    return metadata


@activity.defn
@ingestion_activity
async def push_input_process(
    user: KeycloakUser,
    metadata: DocumentMetadata,
    profile: IngestionProcessingProfile | str | None = None,
    logging_context: str | None = None,
) -> DocumentMetadata:
    """
    Extract the control-plane-authorized original and publish its generation artifacts.
    """
    logger = activity.logger
    started_at = asyncio.get_running_loop().time()
    profile = coerce_processing_profile(profile)
    logger.info("[SCHEDULER][ACTIVITY][PUSH_INPUT_PROCESS] Starting uid=%s profile=%s", metadata.document_uid, profile)

    ingestion_service = await manager_service(metadata.source.source_tag, "extraction")
    if ingestion_service.already_committed:
        metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
        return metadata

    try:
        metadata.set_stage_status(ProcessingStage.PREVIEW_READY, ProcessingStatus.IN_PROGRESS)
        raise_if_document_deleted(await ingestion_service.persist_progress(user, metadata=metadata), metadata.document_uid)

        with tempfile.TemporaryDirectory(prefix=f"doc-{metadata.document_uid}-") as tmpdir:
            working_dir = pathlib.Path(tmpdir)
            input_dir = working_dir / "input"
            output_dir = working_dir / "output"
            input_dir.mkdir(exist_ok=True)
            output_dir.mkdir(exist_ok=True)

            # Only a genuinely absent input is a FileNotFoundError. Wrapping
            # every failure in one made a transient object-store outage look
            # permanent, and a permanent miss look worth six more attempts.
            resolved_input_file = await await_with_heartbeat(
                resolve_push_input_file_for_worker(
                    user=user,
                    metadata=metadata,
                    working_dir=working_dir,
                    ingestion_service=ingestion_service,
                ),
                heartbeat_details={
                    "stage": "push_input_restore",
                    "document_uid": metadata.document_uid,
                },
            )

            await extract_document(
                input_path=resolved_input_file,
                output_dir=output_dir,
                metadata=metadata,
                profile=profile,
                stage="push_input_process",
                started_at=started_at,
                manager_job_json=ingestion_service.extraction_context,
            )
            await to_thread_with_heartbeat(
                ingestion_service.save_output,
                user,
                metadata,
                output_dir,
                heartbeat_details={
                    "stage": "push_input_save_output",
                    "document_uid": metadata.document_uid,
                },
            )

        if not ingestion_service.context.is_tabular_file(metadata.document_name):
            metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
        await ingestion_service.persist_progress(user, metadata=metadata)
        logger.info("[SCHEDULER][ACTIVITY][PUSH_INPUT_PROCESS] completed uid=%s", metadata.document_uid)
        emit_temporal_activity_result_kpis(
            phase="input",
            started_at_monotonic=started_at,
            metadata=metadata,
            status="success",
        )
        return metadata
    except Exception as exc:
        ingestion_service.record_failure(exc)
        error_message = f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"
        metadata.mark_stage_error(ProcessingStage.PREVIEW_READY, error_message)
        try:
            await ingestion_service.persist_progress(user, metadata=metadata)
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
        emit_temporal_activity_result_kpis(
            phase="input",
            started_at_monotonic=started_at,
            metadata=metadata,
            status="error",
            exc=exc,
        )

        raise_permanent_failure(exc)
        raise
