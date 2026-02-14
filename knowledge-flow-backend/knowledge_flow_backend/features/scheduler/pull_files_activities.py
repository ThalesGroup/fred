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
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


async def resolve_pull_input_file_for_worker(
    *,
    metadata: DocumentMetadata,
    working_dir: pathlib.Path,
) -> pathlib.Path:
    source_tag = getattr(metadata.source, "source_tag", None)
    pull_location = getattr(metadata.source, "pull_location", None)
    if not source_tag or not pull_location:
        raise FileNotFoundError(f"Pull input missing source metadata for document {metadata.document_uid}: source_tag={source_tag!r}, pull_location={pull_location!r}.")

    from knowledge_flow_backend.application_context import ApplicationContext

    loader = ApplicationContext.get_instance().get_content_loader(source_tag)
    fetched = await asyncio.to_thread(loader.fetch_by_relative_path, pull_location, working_dir / "input")
    if fetched.exists() and fetched.is_file():
        return fetched

    raise FileNotFoundError(f"Pull input file not found after fetch for document {metadata.document_uid} (source_tag={source_tag}, pull_location={pull_location}).")


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
        metadata = await ingestion_service.extract_metadata(
            file.processed_by,
            full_path,
            tags=file.tags,
            source_tag=file.source_tag,
            profile=file.profile,
        )
        metadata.source.pull_location = file.external_path
        logger.info(f"[SCHEDULER][ACTIVITY][CREATE_PULL_FILE_METADATA] metadata={metadata}")

        await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

        logger.info(f"[SCHEDULER][ACTIVITY][CREATE_PULL_FILE_METADATA] Metadata extracted and saved uid={metadata.document_uid}")
        return metadata


@activity.defn
async def pull_input_process(
    user: KeycloakUser,
    metadata: DocumentMetadata,
    profile: IngestionProcessingProfile | str | None = None,
) -> DocumentMetadata:
    """
    Process pull-file input and persist generated output in content storage.
    The file is always re-fetched on the current worker.
    """
    logger = activity.logger
    logger.info("[SCHEDULER][ACTIVITY][PULL_INPUT_PROCESS] Starting uid=%s", metadata.document_uid)
    logger.info("[SCHEDULER][ACTIVITY][PULL_INPUT_PROCESS] profile=%r type=%s", profile, type(profile).__name__)

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

            try:
                resolved_input_file = await resolve_pull_input_file_for_worker(
                    metadata=metadata,
                    working_dir=working_dir,
                )
            except Exception as exc:
                raise FileNotFoundError(f"Pull input fetch failed for document {metadata.document_uid}.") from exc

            await asyncio.to_thread(
                ingestion_service.process_input,
                user,
                resolved_input_file,
                output_dir,
                metadata,
                profile,
            )
            await asyncio.to_thread(ingestion_service.save_output, user, metadata, output_dir)

        metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)
        await ingestion_service.save_metadata(user, metadata=metadata)
        logger.info("[SCHEDULER][ACTIVITY][PULL_INPUT_PROCESS] completed uid=%s", metadata.document_uid)
        return metadata
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"
        metadata.mark_stage_error(ProcessingStage.PREVIEW_READY, error_message)
        try:
            await ingestion_service.save_metadata(user, metadata=metadata)
        except Exception:
            logger.exception(
                "[SCHEDULER][ACTIVITY][PULL_INPUT_PROCESS] failed to persist error state uid=%s",
                metadata.document_uid,
                exc_info=True,
            )
        logger.exception(
            "[SCHEDULER][ACTIVITY][PULL_INPUT_PROCESS] failed uid=%s",
            metadata.document_uid,
            exc_info=True,
        )
        raise
