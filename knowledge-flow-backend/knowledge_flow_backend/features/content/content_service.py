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

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.stores.content.base_content_store import FileMetadata

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
        mime_type = document_metadata.file.mime_type
        if mime_type == "text/csv":
            csv_bytes = self.content_store.get_preview_bytes(f"{document_uid}/output/table.csv")
            csv_file_like = BytesIO(csv_bytes)
            df = pd.read_csv(csv_file_like, nrows=100)
            preview_str = df.to_markdown(index=False, tablefmt="github")
            if preview_str is None or preview_str.strip() == "":
                preview_str = "_(The CSV file is empty or has no data to display)_"
            return preview_str
        else:
            try:
                return self.content_store.get_preview_bytes(f"{document_uid}/output/output.md").decode("utf-8")
            except FileNotFoundError:
                raise ValueError(f"No preview found for document {document_uid} of type {mime_type} ")

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
