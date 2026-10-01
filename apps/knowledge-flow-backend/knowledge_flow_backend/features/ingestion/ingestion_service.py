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
import re
import threading
from typing import Iterable, Optional, Tuple

from fred_core import KeycloakUser
from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage, SourceType

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.processing_profile_context import coerce_processing_profile, processing_profile_scope
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.core.processing_pipeline_manager import ProcessingPipelineManager
from knowledge_flow_backend.features.metadata.service import MetadataService

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

    async def apply_versioning(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """
        Ensure the incoming document gets a suffix-based version within its primary folder/tag.
        """
        canonical_name, explicit_version = self._split_versioned_name(metadata.identity.document_name)
        primary_tag = self._select_primary_tag(metadata)

        if not primary_tag:
            raise ValueError("A destination folder is required for corpus versioning")
        existing_docs = await self.metadata_service.metadata_store.get_metadata_in_tag(primary_tag)
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

    async def adopt_existing_document(self, user: KeycloakUser, metadata: DocumentMetadata, existing_uid: str) -> DocumentMetadata:
        """Replace an admitted document in its single destination folder, keeping its UID."""
        previous = await self.metadata_service.metadata_store.get_metadata_by_uid(existing_uid)
        if previous is None:
            raise ValueError("The document to replace no longer exists. Start a new import.")
        if previous.kind != "corpus" or previous.tags.tag_ids != metadata.tags.tag_ids:
            raise ValueError("The document to replace no longer belongs to the destination folder. Start a new import.")

        # Clear the recorded stages before purging, but use their original values
        # to identify every artifact the old document actually produced.
        indexed = previous.model_copy(deep=True)
        previous.processing.stages = {}
        if not await self.metadata_service.update_document_metadata_trusted(user, previous):
            raise ValueError("The document to replace no longer exists. Start a new import.")

        metadata.identity.document_uid = existing_uid
        metadata.processing.stages = {}
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

    async def save_metadata_trusted(self, user: KeycloakUser, metadata: DocumentMetadata) -> None:
        """Save inside work already authorized at ingestion/migration admission."""
        logger.debug(f"Saving metadata (trusted) {metadata}")
        return await self.metadata_service.save_document_metadata_trusted(user, metadata)

    async def persist_progress_trusted(self, user: KeycloakUser, metadata: DocumentMetadata) -> bool:
        """Persist admitted work without creating a deleted document again.

        Keep the existing late-writer cleanup: native activity cancellation may
        leave a processing thread finishing after the document was deleted.
        """
        if await self.metadata_service.update_document_metadata_trusted(user, metadata):
            return True
        logger.info(
            "[INGESTION] document_uid=%s was deleted mid-flight; discarding the artifacts this attempt wrote",
            metadata.document_uid,
        )
        await self.metadata_service.purge_document_artifacts(metadata.document_uid)
        return False

    async def get_metadata_trusted(self, document_uid: str) -> DocumentMetadata | None:
        """Read the admitted document inside an ingestion activity."""
        return await self.metadata_service.metadata_store.get_metadata_by_uid(document_uid)

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
        *,
        apply_versioning: bool = True,
    ) -> DocumentMetadata:
        """
        Extracts metadata from the input file.
        This method is responsible for determining the file type and using the appropriate processor
        to extract metadata. It also validates the metadata to ensure it contains a document UID.

        `apply_versioning` keeps the suffix-based draft version a person gets for
        uploading the same name twice. A caller that addresses its documents by a
        source key turns it off: it has one document per key by construction, so
        a second write of that key is the same document again, not a draft beside
        it — and the scan would refuse the third write outright.
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
        if apply_versioning:
            metadata = await self.apply_versioning(metadata)

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
