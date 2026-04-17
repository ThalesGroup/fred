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
import mimetypes
from io import BytesIO
from typing import BinaryIO, Tuple

import pandas as pd
from fred_core import Action, KeycloakUser, Resource, authorize
from tabulate import tabulate

from knowledge_flow_backend.common.document_structures import DocumentMetadata, FileType, ProcessingStage, ProcessingStatus
from knowledge_flow_backend.core.stores.content.base_content_store import FileMetadata
from knowledge_flow_backend.features.tabular.artifacts import read_tabular_artifact

logger = logging.getLogger(__name__)


class ContentService:
    """
    Service for retrieving document content and converting it to markdown.
    Focuses solely on content retrieval and conversion.
    """

    def __init__(self):
        """Initialize content service with necessary stores."""
        from knowledge_flow_backend.application_context import ApplicationContext

        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        self.content_store = ApplicationContext.get_instance().get_content_store()
        self.config = ApplicationContext.get_instance().get_config()
        self._tabular_service = None

    @staticmethod
    def _preview_status(metadata: DocumentMetadata) -> ProcessingStatus:
        return metadata.processing.stages.get(ProcessingStage.PREVIEW_READY, ProcessingStatus.NOT_STARTED)

    @staticmethod
    def _is_tabular_document(metadata: DocumentMetadata) -> bool:
        """
        Return whether one document should use the tabular preview flow.

        Why this exists:
        - Tabular previews are now rendered from indexed Parquet artifacts
          rather than persisted `table.csv` files.

        How to use:
        - Pass the loaded document metadata before selecting the preview path.
        """
        return metadata.file.file_type == FileType.CSV or metadata.file.mime_type == "text/csv"

    @staticmethod
    def _dataframe_to_markdown_preview(df: pd.DataFrame) -> str:
        """
        Convert one bounded DataFrame into the UI markdown preview format.

        Why this exists:
        - Markdown and Parquet-backed tabular previews should share the same
          empty-state formatting.

        How to use:
        - Pass a small preview DataFrame, typically already limited to the
          desired row count.
        """

        def _format_cell(value: object) -> str:
            text = "" if value is None else str(value)
            return text.replace("|", "&#124;").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

        formatted_headers = [_format_cell(name) for name in df.columns.tolist()]
        formatted_rows = [[_format_cell(cell) for cell in row] for row in df.itertuples(index=False, name=None)]
        preview_str = tabulate(formatted_rows, headers=formatted_headers, tablefmt="github")
        if preview_str is None or preview_str.strip() == "":
            return "_(The CSV file is empty or has no data to display)_"
        return preview_str

    def _get_tabular_service(self):
        """
        Lazily return the tabular service used for Parquet-backed previews.

        Why this exists:
        - Content previews need tabular runtime access only for CSV documents.
        - Lazy initialization keeps the default content-service setup light in
          tests that never touch tabular previews.

        How to use:
        - Call before rendering one tabular preview from a Parquet artifact.
        """
        if self._tabular_service is None:
            from knowledge_flow_backend.features.tabular.service import TabularService

            self._tabular_service = TabularService()
        return self._tabular_service

    async def _render_tabular_preview(self, user: KeycloakUser, metadata: DocumentMetadata) -> str:
        """
        Render one tabular preview directly from the indexed Parquet artifact.

        Why this exists:
        - The tabular runtime should not persist a second large preview copy of
          the source CSV just for UI rendering.

        How to use:
        - Call only once `SQL_INDEXED` is done and a `tabular_v1` artifact is
          present on the document metadata.
        """
        preview_frame = await self._get_tabular_service().read_dataset_preview_frame(
            user,
            metadata.document_uid,
            max_rows=200,
        )
        return self._dataframe_to_markdown_preview(preview_frame)

    def _get_preview_bytes(self, document_uid: str, *candidate_names: str) -> tuple[str, bytes]:
        for candidate_name in candidate_names:
            try:
                data = self.content_store.get_preview_bytes(f"{document_uid}/output/{candidate_name}")
                return candidate_name, data
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"No preview artifact found for document {document_uid}. Tried: {', '.join(candidate_names)}")

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_document_metadata(self, user: KeycloakUser, document_uid: str) -> DocumentMetadata:
        """
        Return the metadata dict for a document UID.

        Raises
        -------
        ValueError
            If the UID is empty.
        FileNotFoundError
            If no metadata exists for that UID.
        """
        if not document_uid:
            raise ValueError("Document UID is required")

        metadata = await self.metadata_store.get_metadata_by_uid(document_uid)
        if metadata is None:
            # Let the controller map this to a 404
            raise FileNotFoundError(f"No metadata found for document {document_uid}")
        return metadata

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_original_content(self, user: KeycloakUser, document_uid: str) -> Tuple[BinaryIO, str, str]:
        """
        Returns binary stream of original input file, filename and content type.
        """
        metadata = await self.get_document_metadata(user, document_uid)
        document_name = metadata.document_name
        content_type = mimetypes.guess_type(document_name)[0] or "application/octet-stream"

        try:
            stream = self.content_store.get_content(document_uid)
        except FileNotFoundError:
            raise FileNotFoundError(f"Original input file not found for document {document_uid}")
        return stream, document_name, content_type

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_document_media(self, user: KeycloakUser, document_uid: str, media_id: str) -> Tuple[BinaryIO, str, str]:
        """
        Returns media file associated with a document if it exists.
        """
        content_type = mimetypes.guess_type(media_id)[0] or "application/octet-stream"

        try:
            stream = self.content_store.get_media(document_uid, media_id)
        except FileNotFoundError:
            raise FileNotFoundError(f"No media found for document {document_uid} with media ID {media_id}")

        return stream, media_id, content_type

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_preview_artifact(
        self,
        user: KeycloakUser,
        document_uid: str,
        artifact_path: str,
    ) -> Tuple[BinaryIO, str, str]:
        artifact_name = (artifact_path or "").strip().lstrip("/")
        if not artifact_name:
            raise FileNotFoundError("Preview artifact path is empty.")

        try:
            data = self.content_store.get_preview_bytes(f"{document_uid}/output/{artifact_name}")
        except FileNotFoundError:
            raise FileNotFoundError(f"No preview artifact found for document {document_uid} at path {artifact_name}")

        content_type = mimetypes.guess_type(artifact_name)[0] or "application/octet-stream"
        return BytesIO(data), artifact_name.split("/")[-1], content_type

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_markdown_preview(self, user: KeycloakUser, document_uid: str) -> str:
        """
        Return a markdown preview of the document.
        For CSV files, returns the first 200 rows as a markdown table.
        For other files, returns the generated markdown preview.

        This method raises FileNotFoundError if no preview is found.

        The usage is to help the end user (if he is authorized) to quickly see
        a preview of the document content without downloading the full file.
        """
        document_metadata = await self.get_document_metadata(user, document_uid)
        if not document_metadata:
            raise FileNotFoundError(f"No metadata found for document {document_uid}")
        if self._is_tabular_document(document_metadata):
            sql_indexed_status = document_metadata.processing.stages.get(ProcessingStage.SQL_INDEXED, ProcessingStatus.NOT_STARTED)
            if sql_indexed_status == ProcessingStatus.DONE and read_tabular_artifact(document_metadata) is not None:
                return await self._render_tabular_preview(user, document_metadata)

        preview_status = self._preview_status(document_metadata)
        if preview_status != ProcessingStatus.DONE:
            raise FileNotFoundError(f"Preview not ready for document {document_uid}. Current preview stage: {preview_status.value}.")
        mime_type = document_metadata.file.mime_type
        if self._is_tabular_document(document_metadata):
            try:
                candidate_name, preview_bytes = self._get_preview_bytes(
                    document_uid,
                    "table.csv",
                    "output.md",
                    "output.txt",
                )
            except FileNotFoundError:
                raise FileNotFoundError(f"No preview found for document {document_uid} of type {mime_type}.")

            if candidate_name == "table.csv":
                csv_file_like = BytesIO(preview_bytes)
                df = pd.read_csv(csv_file_like, nrows=200)
                return self._dataframe_to_markdown_preview(df)
            return preview_bytes.decode("utf-8")

        try:
            _, preview_bytes = self._get_preview_bytes(document_uid, "output.md", "output.txt")
            return preview_bytes.decode("utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(f"No preview found for document {document_uid} of type {mime_type}.")

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_file_metadata(self, user: KeycloakUser, document_uid: str) -> FileMetadata:
        # Access control gate (keeps semantics consistent)
        await self.get_document_metadata(user, document_uid)
        meta = self.content_store.get_file_metadata(document_uid)
        if not meta.content_type:
            import mimetypes

            guessed = mimetypes.guess_type(meta.file_name)[0]
            meta.content_type = guessed or "application/octet-stream"
        return meta

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_full_stream(self, user: KeycloakUser, document_uid: str) -> BinaryIO:
        await self.get_document_metadata(user, document_uid)
        return self.content_store.get_content(document_uid)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_range_stream(self, user: KeycloakUser, document_uid: str, *, start: int, length: int) -> BinaryIO:
        await self.get_document_metadata(user, document_uid)
        if start < 0 or length <= 0:
            raise ValueError("Invalid byte range requested.")
        return self.content_store.get_content_range(document_uid, start=start, length=length)
