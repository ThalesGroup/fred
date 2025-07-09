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
from typing import BinaryIO, Dict, Tuple

from app.core.stores.content.content_storage_factory import get_content_store


logger = logging.getLogger(__name__)


class ContentService:
    """
    Service for retrieving document content and converting it to markdown.
    Focuses solely on content retrieval and conversion.
    """

    def __init__(self):
        """Initialize content service with necessary stores."""
        from app.application_context import ApplicationContext

        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        self.content_store = get_content_store()
        self.config = ApplicationContext.get_instance().get_config()

    async def get_document_metadata(self, document_uid: str) -> Dict:
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

        metadata = self.metadata_store.get_metadata_by_uid(document_uid)
        if metadata is None:
            # Let the controller map this to a 404
            raise FileNotFoundError(
                f"No metadata found for document {document_uid}"
            )

        # Optional: ensure the dict has a name; keep if you need it
        metadata.setdefault("document_name", f"{document_uid}.xxx")
        return metadata

    async def get_original_content(self, document_uid: str) -> Tuple[BinaryIO, str, str]:
        """
        Returns binary stream of original input file, filename and content type.
        """
        metadata = await self.get_document_metadata(document_uid)
        document_name = metadata["document_name"]
        content_type = mimetypes.guess_type(document_name)[0] or "application/octet-stream"

        try:
            stream = self.content_store.get_content(document_uid)
        except FileNotFoundError:
            raise FileNotFoundError(f"Original input file not found for document {document_uid}")
        return stream, document_name, content_type

    async def get_markdown_preview(self, document_uid: str) -> str:
        """
        Returns content of output.md if it exists (as markdown).
        """
        try:
            return self.content_store.get_markdown(document_uid)
        except FileNotFoundError:
            raise FileNotFoundError(f"No markdown preview found for document {document_uid}")
