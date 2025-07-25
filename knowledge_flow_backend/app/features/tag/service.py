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

from datetime import datetime
from uuid import uuid4

from app.application_context import ApplicationContext
from app.common.structures import DocumentMetadata
from app.features.metadata.service import MetadataService
from app.features.tag.structure import Tag, TagCreate, TagUpdate, TagWithDocumentsId
from fred_core import KeycloakUser


class TagService:
    """
    Service for Tag resource CRUD operations, user-scoped.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()

        self.document_metadata_service = MetadataService()

    def list_tags_for_user(self, user: KeycloakUser) -> list[TagWithDocumentsId]:
        # Todo: check if user is authorized

        tags = self._tag_store.list_tags_for_user(user)
        tag_with_documents = []
        for tag in tags:
            document_ids = self._retrieve_document_ids_for_tag(tag.id)
            tag_with_documents.append(TagWithDocumentsId.from_tag(tag, document_ids))
        return tag_with_documents

    def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithDocumentsId:
        # Todo: check if user is authorized

        tag = self._tag_store.get_tag_by_id(tag_id)
        document_ids = self._retrieve_document_ids_for_tag(tag_id)
        return TagWithDocumentsId.from_tag(tag, document_ids)

    def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithDocumentsId:
        # Todo: check if user is authorized to create tags

        # Check that document ids are valid
        documents = self._retrieve_documents_metadata(tag_data.document_ids)

        # Create tag from input data
        now = datetime.now()
        tag = self._tag_store.create_tag(Tag(
            name=tag_data.name,
            description=tag_data.description,
            type=tag_data.type,
            # Set a unique id
            id=str(uuid4()),
            # Associate to user
            owner_id=user.uid,
            # Set timestamps
            created_at=now,
            updated_at=now,
        ))

        # Add new tag id to each document metadata
        for doc in documents:
            self._add_tag_id_to_document(doc, tag.id)

        return TagWithDocumentsId.from_tag(tag, tag_data.document_ids)

    def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithDocumentsId:
        # Todo: check if user is authorized

        # Retrieve existing document IDs from the tag
        old_document_ids = self._retrieve_document_ids_for_tag(tag_id)

        # Compute the difference in document IDs
        added, removed = self._compute_document_ids_diff(old_document_ids, tag_data.document_ids)

        # Retrieve docs that need change + Check that added document ids are valid
        added_documents = self._retrieve_documents_metadata(added)
        removed_documents = self._retrieve_documents_metadata(removed)

        for doc in added_documents:
            self._add_tag_id_to_document(doc, tag_id)

        for doc in removed_documents:
            self._remove_tag_id_from_document(doc, tag_id)

        # Retrieve the existing tag
        tag = self._tag_store.get_tag_by_id(tag_id)

        # Update tag with input data
        tag.name = tag_data.name
        tag.description = tag_data.description
        tag.type = tag_data.type
        # tag.document_ids = tag_data.document_ids
        # Update the updated_at timestamp
        tag.updated_at = datetime.now()

        updated_tag = self._tag_store.update_tag_by_id(tag_id, tag)
        return TagWithDocumentsId.from_tag(updated_tag, tag_data.document_ids)

    def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        # Todo: check if user is authorized
        
        # Remove the tag ID from all documents that have this tag
        documents = self._retrieve_documents_for_tag(tag_id)
        for doc in documents:
            self._remove_tag_id_from_document(doc, tag_id)
        
        return self._tag_store.delete_tag_by_id(tag_id)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Util private methods

    def _retrieve_documents_for_tag(self, tag_id: str) -> list[DocumentMetadata]:
        """
        Retrieve the document associated with a tag.
        """
        return self.document_metadata_service.get_document_metadata_in_tag(tag_id)

    def _retrieve_document_ids_for_tag(self, tag_id: str) -> list[str]:
        """
        Retrieve the document IDs associated with a tag.
        """
        documents = self._retrieve_documents_for_tag(tag_id)
        return [doc.document_uid for doc in documents]

    def _retrieve_documents_metadata(self, document_ids: list[str]) -> list[DocumentMetadata]:
        """
        Retrieve full document metadata for a list of document IDs.
        """
        metadata = []
        for doc_id in document_ids:
            # If document id doesn't exist, a `MetadataNotFound` exception will be raised
            metadata.append(self.document_metadata_service.get_document_metadata(doc_id))
        return metadata

    @staticmethod
    def _compute_document_ids_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
        """
        Compute the difference between two lists of document IDs.
        Returns a tuple of (to_add, to_remove).
        """
        before_set = set(before)
        after_set = set(after)

        added = list(after_set - before_set)
        removed = list(before_set - after_set)

        return added, removed

    def _add_tag_id_to_document(self, document: DocumentMetadata, new_tag_id: str) -> None:
        """
        Add a tag ID to a document's metadata.
        """
        existing_tags = document.tags or []
        self.document_metadata_service.update_document_metadata(document.document_uid, {"tags": existing_tags + [new_tag_id]})

    def _remove_tag_id_from_document(self, document: DocumentMetadata, tag_id: str) -> None:
        """
        Remove a tag ID from a document's metadata.
        """
        existing_tags = document.tags or []
        if tag_id in existing_tags:
            existing_tags.remove(tag_id)
            self.document_metadata_service.update_document_metadata(document.document_uid, {"tags": existing_tags})
        else:
            raise ValueError(f"Tag ID {tag_id} not found in document {document.document_uid} tags.")
