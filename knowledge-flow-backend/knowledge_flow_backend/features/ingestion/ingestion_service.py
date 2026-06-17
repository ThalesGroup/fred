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

import logging
import pathlib
import re
import threading
from typing import Iterable, Optional, Tuple

from fred_core import Action, KeycloakUser, Resource, TagPermission, authorize

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus, SourceType
from knowledge_flow_backend.common.processing_profile_context import coerce_processing_profile, processing_profile_scope
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.core.processing_pipeline_manager import ProcessingPipelineManager
from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import ProcessDocumentsProgressResponse
from knowledge_flow_backend.features.scheduler.workflow_status import (
    WORKFLOW_STATUS_COMPLETED,
    is_non_terminal_status,
    is_terminal_failure_status,
)

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
        # Library-aware pipeline manager. For now it contains only the default
        # pipeline mirroring legacy behaviour, but it is ready to support
        # per-library pipelines via tag-based routing.
        self.pipeline_manager = ProcessingPipelineManager.create_with_default(self.context)

    @staticmethod
    def _split_versioned_name(name: str) -> Tuple[str, int]:
        """
        Return (canonical_name, version) from a display name like 'report.docx (2)'.
        Defaults to version=0 when no suffix is present.
        """
        match = re.match(r"^(?P<base>.+)\s\((?P<version>\d+)\)$", name.strip())
        if match:
            return match.group("base"), int(match.group("version"))
        return name, 0

    def _select_primary_tag(self, metadata: DocumentMetadata) -> str | None:
        tags = metadata.tags.tag_ids or []
        return tags[0] if tags else None

    def _existing_versions(self, canonical_name: str, primary_tag: str | None, docs: Iterable[DocumentMetadata]) -> list[int]:
        """
        Collect known versions of the same canonical name within the same primary tag (folder).
        Falls back to parsing the display name when older docs don't carry canonical/version fields.
        """
        versions: list[int] = []
        for d in docs:
            if primary_tag and primary_tag not in (d.tags.tag_ids or []):
                continue

            canon_field = getattr(d.identity, "canonical_name", None)
            canon = self._split_versioned_name(canon_field)[0] if canon_field else self._split_versioned_name(d.identity.document_name)[0]
            if canon != canonical_name:
                continue

            version = getattr(d.identity, "version", None)
            if version is None:
                version = self._split_versioned_name(d.identity.document_name)[1]
            versions.append(max(0, int(version)))
        return versions

    async def _apply_versioning(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """
        Ensure the incoming document gets a suffix-based version within its primary folder/tag.
        """
        canonical_name, explicit_version = self._split_versioned_name(metadata.identity.document_name)
        primary_tag = self._select_primary_tag(metadata)

        filters = {}
        if primary_tag:
            filters = {"tags": {"tag_ids": [primary_tag]}}

        existing_docs = await self.metadata_service.metadata_store.get_all_metadata(filters)
        existing_versions = self._existing_versions(canonical_name, primary_tag, existing_docs)

        # Prevent cascading (2), (3)… — keep at most one alternate version (1)
        if explicit_version > 1 or any(v > 0 for v in existing_versions):
            raise ValueError(f"A draft version already exists for '{canonical_name}'. Delete or promote it before ingesting another version.")

        version = 1 if existing_versions else 0
        display_name = canonical_name  # keep original name; UI will use version field to render badge

        metadata.identity.canonical_name = canonical_name
        metadata.identity.version = version
        metadata.identity.document_name = display_name
        return metadata

    @authorize(Action.CREATE, Resource.DOCUMENTS)
    def save_input(self, user: KeycloakUser, metadata: DocumentMetadata, input_dir: pathlib.Path) -> None:
        self.content_store.save_input(metadata.document_uid, input_dir)
        metadata.mark_stage_done(ProcessingStage.RAW_AVAILABLE)

    @authorize(Action.CREATE, Resource.DOCUMENTS)
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

    @authorize(Action.CREATE, Resource.DOCUMENTS)
    async def save_metadata(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        logger.debug(f"Saving metadata {metadata}")
        return await self.metadata_service.save_document_metadata(user, metadata)

    async def ensure_can_write_tags(self, user: KeycloakUser, tag_ids: list[str]) -> None:
        """Fail fast (raises AuthorizationError -> 403) if the user cannot write the target tags.

        save_document_metadata enforces the same TagPermission.UPDATE check, but only
        after extraction and raw-file persistence have run. Checking up-front avoids
        doing (and partially persisting) work for an unauthorized request.
        """
        for tag_id in tag_ids:
            await self.metadata_service.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.READ, Resource.DOCUMENTS)
    def get_local_copy(self, user: KeycloakUser, metadata: DocumentMetadata, target_dir: pathlib.Path) -> pathlib.Path:
        """
        Downloads the file content from the store into target_dir and returns the path to the file.
        """
        return self.content_store.get_local_copy(metadata.document_uid, target_dir)

    @authorize(Action.CREATE, Resource.DOCUMENTS)
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

        # Step 1: run processor
        metadata = processor.process_metadata(file_path, tags=tags, source_tag=source_tag)
        metadata = await self._apply_versioning(metadata)

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

    @authorize(Action.CREATE, Resource.DOCUMENTS)
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
        """
        normalized_profile = coerce_processing_profile(profile)
        with processing_profile_scope(normalized_profile):
            pipeline = self.pipeline_manager.get_pipeline_for_metadata(metadata, profile=normalized_profile)
            pipeline.process_input(input_path=input_path, output_dir=output_dir, metadata=metadata)

    @authorize(Action.CREATE, Resource.DOCUMENTS)
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
            pipeline = self.pipeline_manager.get_pipeline_for_metadata(input_file_metadata, profile=normalized_profile)
            return pipeline.process_output(
                input_file_name=input_file_name,
                output_dir=output_dir,
                input_file_metadata=input_file_metadata,
            )

    @authorize(Action.READ, Resource.DOCUMENTS)
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

    @authorize(Action.CREATE, Resource.DOCUMENTS)
    async def get_processing_progress(
        self,
        user: KeycloakUser,
        scheduler_task_service: IngestionTaskService | None,
        workflow_id: str | None,
    ) -> ProcessDocumentsProgressResponse:
        if scheduler_task_service is None:
            raise ValueError("Scheduler backend is disabled")
        return await scheduler_task_service.get_progress(user=user, workflow_id=workflow_id)

    def _failure_stage(self, metadata: DocumentMetadata) -> ProcessingStage:
        """Stage to flag when a document's processing did not complete.

        We mark the document's terminal *output* stage. Reconciliation only fails
        documents that are not yet "ready" (neither vector nor sql done), so this
        stage is guaranteed not already DONE — we never overwrite a completed
        stage, and the document's overall status resolves to FAILED.
        """
        if self.context.is_tabular_file(metadata.document_name):
            return ProcessingStage.SQL_INDEXED
        return ProcessingStage.VECTORIZED

    def mark_processing_failed(self, metadata: DocumentMetadata, msg: str) -> None:
        """Durably flag a document as failed (in-memory mutation; caller persists)."""
        metadata.mark_stage_error(self._failure_stage(metadata), msg)

    @staticmethod
    def _is_processing_terminal(metadata: DocumentMetadata) -> bool:
        """A document is terminal when it is ready (vector|sql done) or has a failed stage."""
        stages = metadata.processing.stages
        if stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE or stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE:
            return True
        return any(value == ProcessingStatus.FAILED for value in stages.values())

    @staticmethod
    def _reconciled_failure_message(status: Optional[str], last_error: Optional[str]) -> Optional[str]:
        """Decide whether a workflow status means a still-pending doc must be failed.

        Returns the failure message to record, or None to leave the document as-is.
        - None / non-terminal status -> None (unreachable or still running; never false-fail).
        - terminal failure           -> detailed error if available, else "Processing workflow <STATUS>".
        - COMPLETED                  -> inconsistency message (workflow done but doc not processed).
        """
        if status is None or is_non_terminal_status(status):
            return None
        if is_terminal_failure_status(status):
            if last_error and last_error.strip():
                return last_error.strip()
            return f"Processing workflow {status}"
        if status == WORKFLOW_STATUS_COMPLETED:
            return "Processing workflow finished but the document was not fully processed"
        return None

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def reconcile_tag_processing(
        self,
        user: KeycloakUser,
        scheduler_task_service: IngestionTaskService | None,
        tag_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[DocumentMetadata], int]:
        """List a folder's documents and reconcile non-terminal ones against Temporal.

        This is the durability guarantee for "leave and come back": a document can
        never stay pending in fred while its Temporal workflow is gone/failed.

        For each still-non-terminal document that carries a ``workflow_id``, we ask
        Temporal (a client ``describe`` call — works even when the worker is down)
        for the workflow's real status and reflect it:
          - terminal failure (FAILED/TIMED_OUT/CANCELED/TERMINATED) -> mark FAILED.
          - COMPLETED but the document never finished -> mark FAILED (inconsistent).
          - RUNNING / non-terminal -> leave as-is (trust Temporal's own timeout).
          - status unknown (Temporal unreachable) -> leave as-is (never false-fail).

        Persistence is best-effort: the returned documents always reflect the
        corrected status (so the UI is correct immediately), and we persist the
        heal when the caller is allowed to write.
        """
        docs, total = await self.metadata_service.browse_documents_in_tag(user, tag_id=tag_id, offset=offset, limit=limit)
        await self._reconcile_documents(user, scheduler_task_service, docs)
        return docs, total

    async def _reconcile_documents(
        self,
        user: KeycloakUser,
        scheduler_task_service: IngestionTaskService | None,
        docs: list[DocumentMetadata],
    ) -> None:
        """Reconcile a list of documents against Temporal (mutates + best-effort persists).

        Split out from the decorated browse wrapper so the reconciliation glue is
        unit-testable without the authorization layer.
        """
        if scheduler_task_service is None:
            return

        # One describe per distinct workflow, only for non-terminal docs with a link.
        pending_by_workflow: dict[str, list[DocumentMetadata]] = {}
        for doc in docs:
            workflow_id = doc.processing.workflow_id
            if not workflow_id or self._is_processing_terminal(doc):
                continue
            pending_by_workflow.setdefault(workflow_id, []).append(doc)

        for workflow_id, workflow_docs in pending_by_workflow.items():
            try:
                status = await scheduler_task_service.get_workflow_status(workflow_id=workflow_id)
            except Exception:
                logger.warning("[RECONCILE] Failed to query workflow status workflow_id=%s", workflow_id, exc_info=True)
                continue

            # Only fetch the detailed error when the status is a terminal failure.
            last_error: Optional[str] = None
            if is_terminal_failure_status(status):
                try:
                    last_error = await scheduler_task_service.get_workflow_last_error(workflow_id=workflow_id)
                except Exception:
                    last_error = None

            msg = self._reconciled_failure_message(status, last_error)
            if msg is None:
                continue

            for doc in workflow_docs:
                self.mark_processing_failed(doc, msg)
                try:
                    await self.save_metadata(user, metadata=doc)
                except Exception:
                    logger.warning("[RECONCILE] Could not persist failed status doc=%s", doc.document_uid, exc_info=True)


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
