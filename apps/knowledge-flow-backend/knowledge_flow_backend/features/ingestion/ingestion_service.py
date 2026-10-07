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
import threading
from typing import Optional

from fred_core import KeycloakUser
from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage, SourceType

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.processing_profile_context import coerce_processing_profile, processing_profile_scope
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.core.processing_pipeline_manager import ProcessingPipelineManager
from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService

logger = logging.getLogger(__name__)


class IngestionService:
    """
    A simple service to help ingesting new files.
    ----------------
    This service is responsible for the inital steps of the ingestion process:
    1. Saving the uploaded file to a temporary directory.
    2. Extracting metadata from the file using the appropriate processor based on the file extension.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.content_store = ApplicationContext.get_instance().get_content_store()
        self.metadata_service = MetadataService()
        # Shared pipeline manager for the configured processing profiles.
        self.pipeline_manager = ProcessingPipelineManager.create_with_default(self.context)

    async def adopt_existing_document(self, user: KeycloakUser, metadata: DocumentMetadata, existing_uid: str) -> DocumentMetadata:
        """Make a freshly-extracted document *be* the one it replaces.

        Keeping the uid is the whole reason to prefer replacing to
        delete-then-create: every citation and link already pointing at that
        document keeps resolving, and now resolves to the new content.

        Replacing content is not moving the document: it keeps every library it
        was in, plus the one it is being imported into. Dropping the others
        would remove it from them, quota and ReBAC grants included, which
        nobody asked for.

        Order matters. The row is marked unprocessed *before* the index is
        dropped, so a failure between the two leaves a document that says it
        has nothing indexed — which is then true — rather than one claiming
        vectors it no longer has. The bytes themselves stay until `save_input`
        overwrites them, so the document is never without content.

        Returns the metadata unchanged when the document has been deleted since
        the import was planned — there is then nothing to replace.
        """
        previous = await self.metadata_service.metadata_store.get_metadata_by_uid(existing_uid)
        if previous is None:
            return metadata

        # Probe before adopting anything. Taking the uid and the libraries first
        # would leave the bail-out below returning metadata that impersonates a
        # document someone just deleted — saving it recreates that row and puts
        # it back in every library it was in, none of them asked for.
        # What it had indexed, kept before the row stops claiming it:
        # purge_document_artifacts skips a store for a stage the document never
        # reached, so handing it the cleared row would skip every one of them
        # and leave the old vectors answering under the new content's uid.
        indexed = previous.model_copy(deep=True)

        previous.processing.stages = {}
        if not await self.persist_progress(user, previous):
            # Deleted between the read above and this write: nothing to replace,
            # and nothing of ours to purge.
            return metadata

        metadata.identity.document_uid = existing_uid
        metadata.processing.stages = {}
        metadata.tags.tag_ids = list(dict.fromkeys([*(previous.tags.tag_ids or []), *(metadata.tags.tag_ids or [])]))
        await self.metadata_service.purge_document_artifacts(existing_uid, metadata=indexed, include_content=False)
        return metadata

    def save_input(self, user: KeycloakUser, metadata: DocumentMetadata, input_dir: pathlib.Path) -> None:
        self.content_store.save_input(metadata.document_uid, input_dir)
        metadata.mark_stage_done(ProcessingStage.RAW_AVAILABLE)

    def save_output(self, user: KeycloakUser, metadata: DocumentMetadata, output_dir: pathlib.Path) -> None:
        """
        Persist the input-stage output directory for one document.

        Why this exists:
        - Markdown flows still need their generated preview artifacts copied to
          content storage after the input stage.
        - Tabular flows may keep `output_dir` empty because previews are
          derived later from the indexed Parquet artifact.

        How to use:
        - Pass the current user, document metadata, and local `output_dir`.
        - The method marks `PREVIEW_READY` only when the input stage actually
          produced a persisted preview artifact.
        """
        self.content_store.save_output(metadata.document_uid, output_dir)
        if not self.context.is_tabular_file(metadata.document_name):
            metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)

    async def save_metadata(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        logger.debug(f"Saving metadata {metadata}")
        return await self.metadata_service.save_document_metadata(user, metadata)

    async def persist_progress(self, user: KeycloakUser, metadata: DocumentMetadata) -> bool:
        """Persist an ingestion in flight, or clean up after a lost race (#2315).

        The single seam every ingestion-progress write goes through. It never
        creates a document: `update_document_metadata` is a conditional UPDATE,
        so a document deleted meanwhile stays deleted and this returns False.

        When that happens the caller has already written artifacts (content,
        vectors, Parquet) for a document that no longer exists — its work runs
        in a thread Python cannot kill, so it routinely finishes after a
        cancellation erased the document. Those bytes are orphans nothing points
        at, so the writer that lost the race discards its own output here rather
        than leaving it for the corpus audit to report.

        Returns whether the document is still there, for callers that want to
        stop early.
        """
        return await self._persist_progress(self.metadata_service.update_document_metadata, user, metadata)

    async def _persist_progress(self, update, user: KeycloakUser, metadata: DocumentMetadata) -> bool:
        if await update(user, metadata):
            return True
        logger.info(
            "[INGESTION] document_uid=%s was deleted mid-flight; discarding the artifacts this attempt wrote",
            metadata.document_uid,
        )
        await self.metadata_service.purge_document_artifacts(metadata.document_uid)
        return False

    async def get_metadata(self, user: KeycloakUser, document_uid: str) -> DocumentMetadata | None:
        """
        Retrieve the metadata associated with the given document UID.

        Args:
            document_uid (str): The unique identifier of the document.

        Returns:
            Optional[DocumentMetadata]: The metadata if found, or None if the document
            does not exist in the metadata store.

        Notes:
            If the underlying metadata service raises a `MetadataNotFound` exception,
            this method will return `None` instead of propagating the exception.
        """

        try:
            return await self.metadata_service.get_document_metadata(user, document_uid)
        except MetadataNotFound:
            return None

    def get_local_copy(self, user: KeycloakUser, metadata: DocumentMetadata, target_dir: pathlib.Path) -> pathlib.Path:
        """
        Downloads the file content from the store into target_dir and returns the path to the file.
        """
        return self.content_store.get_local_copy(metadata.document_uid, target_dir)

    async def extract_metadata(
        self,
        user: KeycloakUser,
        file_path: pathlib.Path,
        tags: list[str],
        source_tag: str,
        profile: IngestionProcessingProfile | str | None = None,
    ) -> DocumentMetadata:
        """
        Extracts metadata from the input file.
        This method is responsible for determining the file type and using the appropriate processor
        to extract metadata. It also validates the metadata to ensure it contains a document UID.
        """
        suffix = file_path.suffix.lower()
        normalized_profile = coerce_processing_profile(profile)
        pipeline = self.pipeline_manager.get_pipeline_for_profile(normalized_profile)
        processor = pipeline.get_input_processor(suffix)
        source_config = self.context.get_config().document_sources.get(source_tag)

        # Step 1: run processor — off the loop, since it hashes the whole file twice
        # and opens PDF/DOCX, which would stall every other request meanwhile.
        metadata = await asyncio.to_thread(processor.process_metadata, file_path, tags=tags, source_tag=source_tag)
        # Stamped once, here, regardless of file type — not delegated to any
        # per-processor extract_file_metadata(), which only ever sees the
        # file's own embedded metadata, never who is uploading it.
        metadata.identity.uploaded_by = user.uid
        metadata.processing.profile = normalized_profile

        # Step 2: enrich/clean metadata
        if source_config:
            metadata.source.source_type = SourceType(source_config.type)

        # If this is a pull file, preserve the path
        if source_config and source_config.type == "pull":
            metadata.source.pull_location = str(file_path.name)

        # Clean string fields like "None" to actual None
        for field in ["title", "category", "subject", "keywords"]:
            value = getattr(metadata, field, None)
            if isinstance(value, str) and value.strip().lower() == "none":
                setattr(metadata, field, None)

        return metadata

    def process_input(
        self,
        user: KeycloakUser,
        input_path: pathlib.Path,
        output_dir: pathlib.Path,
        metadata: DocumentMetadata,
        profile: IngestionProcessingProfile | str | None = None,
    ) -> None:
        """
        Processes an input document from input_path and writes outputs to output_dir.
        Saves metadata.json alongside.

        The work itself lives on the pipeline manager, which the extraction
        subprocess also calls: one implementation, whichever process runs it.
        """
        self.pipeline_manager.run_input(
            input_path=input_path,
            output_dir=output_dir,
            metadata=metadata,
            profile=profile,
        )

    def process_output(
        self,
        user: KeycloakUser,
        input_file_name: str,
        output_dir: pathlib.Path,
        input_file_metadata: DocumentMetadata,
        profile: IngestionProcessingProfile | str | None = None,
    ) -> DocumentMetadata:
        """
        Processes data resulting from the input processing.
        """
        normalized_profile = coerce_processing_profile(profile)
        with processing_profile_scope(normalized_profile):
            pipeline = self.pipeline_manager.get_pipeline_for_profile(normalized_profile)
            return pipeline.process_output(
                input_file_name=input_file_name,
                output_dir=output_dir,
                input_file_metadata=input_file_metadata,
            )

    def get_preview_file(self, user: KeycloakUser, metadata: DocumentMetadata, output_dir: pathlib.Path) -> pathlib.Path:
        """
        Returns the preview file (output.md or table.csv) for a document.
        Raises if not found.
        """
        for name in ["output.md", "table.csv", "output.txt"]:
            candidate = output_dir / name
            if candidate.exists() and candidate.is_file():
                return candidate
        raise FileNotFoundError(f"No preview file found for document: {metadata.document_uid} did you generate an output file named 'output.md' or 'table.csv'?")


_INGESTION_SERVICE_LOCK = threading.Lock()
_INGESTION_SERVICE_SINGLETON: Optional[IngestionService] = None


def get_ingestion_service(*, force_new: bool = False) -> IngestionService:
    """
    Return a process-local cached IngestionService.

    Temporal activities and API handlers run in separate processes, so each process
    keeps its own singleton. If ApplicationContext is reinitialized (tests), the
    cached service is automatically refreshed against the new context.
    """
    global _INGESTION_SERVICE_SINGLETON

    context = ApplicationContext.get_instance()
    with _INGESTION_SERVICE_LOCK:
        stale_context = _INGESTION_SERVICE_SINGLETON is not None and _INGESTION_SERVICE_SINGLETON.context is not context
        if force_new or _INGESTION_SERVICE_SINGLETON is None or stale_context:
            _INGESTION_SERVICE_SINGLETON = IngestionService()
            logger.debug(
                "[INGESTION][SERVICE] Created process-local singleton force_new=%s stale_context=%s",
                force_new,
                stale_context,
            )
        return _INGESTION_SERVICE_SINGLETON


def reset_ingestion_service() -> None:
    """Clear the cached process-local IngestionService (useful in tests)."""
    global _INGESTION_SERVICE_SINGLETON
    with _INGESTION_SERVICE_LOCK:
        _INGESTION_SERVICE_SINGLETON = None
