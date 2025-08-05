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
from app.common.document_structures import DocumentMetadata
from app.features.metadata.service import MetadataService
from app.features.prompts.service import PromptService
from app.features.prompts.structure import Prompt
from app.features.tag.structure import Tag, TagCreate, TagType, TagUpdate, TagWithItemsId
from fred_core import KeycloakUser


class TagService:
    """
    Service for Tag resource CRUD operations, user-scoped.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()

        self.document_metadata_service = MetadataService()
        self.prompt_service = PromptService()

    def list_all_tags_for_user(self, user: KeycloakUser, tag_type: TagType | None) -> list[TagWithItemsId]:
        """
        List all tags for a user, optionally filtered by tag type.
        Args:
            user (KeycloakUser): The user for whom to list tags.
            tag_type (TagType | None): Optional filter for tag type (e.g., DOCUMENT, PROMPT).
        Returns:
            List[TagWithItemsId]: A list of tags with associated item IDs.
        """
        # Todo: check if user is authorized

        tags = self._tag_store.list_tags_for_user(user)
        tag_with_ids = []

        for tag in tags:
            if tag_type is None or tag.type == tag_type:
                if tag.type == TagType.DOCUMENT:
                    item_ids = self._retrieve_document_ids_for_tag(tag.id)
                elif tag.type == TagType.PROMPT:
                    item_ids = self._retrieve_prompt_ids_for_tag(tag.id)
                else:
                    raise ValueError(f"Unsupported tag type: {tag.type}")
                tag_with_ids.append(TagWithItemsId.from_tag(tag, item_ids))

        return tag_with_ids

    def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithItemsId:
        """
        Get a specific tag by ID for a user.
        Args:
            tag_id (str): The ID of the tag to retrieve.
            user (KeycloakUser): The user for whom to retrieve the tag.
        Returns:
            TagWithItemsId: The tag with associated item IDs.
        Raises:
            TagNotFoundError: If the tag does not exist.
        """
        # Todo: check if user is authorized

        tag = self._tag_store.get_tag_by_id(tag_id)
        if tag.type == TagType.DOCUMENT:
            item_ids = self._retrieve_document_ids_for_tag(tag_id)
        elif tag.type == TagType.PROMPT:
            item_ids = self._retrieve_prompt_ids_for_tag(tag_id)
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")
        return TagWithItemsId.from_tag(tag, item_ids)

    def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithItemsId:
        # Todo: check if user is authorized to create tags

        # Check that document ids are valid
        documents = self._retrieve_documents_metadata(tag_data.item_ids)

        # Create tag from input data
        now = datetime.now()
        tag = self._tag_store.create_tag(
            Tag(
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
            )
        )

        # Add new tag id to each document metadata
        for doc in documents:
            self.document_metadata_service.add_tag_id_to_document(metadata=doc, new_tag_id=tag.id, modified_by=user.username)

        return TagWithItemsId.from_tag(tag, tag_data.item_ids)

    def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithItemsId:
        # Todo: check if user is authorized

        tag = self._tag_store.get_tag_by_id(tag_id)

        if tag.type == TagType.DOCUMENT:
            old_item_ids = self._retrieve_document_ids_for_tag(tag_id)
            added, removed = self._compute_document_ids_diff(old_item_ids, tag_data.item_ids)

            added_documents = self._retrieve_documents_metadata(added)
            removed_documents = self._retrieve_documents_metadata(removed)

            for doc in added_documents:
                self.document_metadata_service.add_tag_id_to_document(metadata=doc, new_tag_id=tag.id, modified_by=user.username)

            for doc in removed_documents:
                self.document_metadata_service.remove_tag_id_from_document(metadata=doc, tag_id_to_remove=tag.id, modified_by=user.username)

        elif tag.type == TagType.PROMPT:
            old_item_ids = self._retrieve_prompt_ids_for_tag(tag_id)
            added, removed = self._compute_document_ids_diff(old_item_ids, tag_data.item_ids)

            for prompt_id in added:
                self.prompt_service.add_tag_to_prompt(prompt_id, tag_id)

            for prompt_id in removed:
                self.prompt_service.remove_tag_from_prompt(prompt_id, tag_id)

        # Update the tag metadata
        tag.name = tag_data.name
        tag.description = tag_data.description
        tag.updated_at = datetime.now()
        updated_tag = self._tag_store.update_tag_by_id(tag_id, tag)
        return TagWithItemsId.from_tag(updated_tag, tag_data.item_ids)

    def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        # Todo: check if user is authorized
        tag = self._tag_store.get_tag_by_id(tag_id)

        if tag.type == TagType.DOCUMENT:
            # Remove the tag ID from all documents that have this tag
            documents = self._retrieve_documents_for_tag(tag_id)
            for doc in documents:
                self.document_metadata_service.remove_tag_id_from_document(metadata=doc, tag_id_to_remove=tag_id, modified_by=user.username)

        elif tag.type == TagType.PROMPT:
            # Remove the tag from all prompts that have this tag
            prompts = self._retrieve_prompts_for_tag(tag_id)
            for prompt in prompts:
                self.prompt_service.remove_tag_from_prompt(prompt.id, tag_id)
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")
        # Finally, delete the tag itself
        try:
            self._tag_store.delete_tag_by_id(tag_id)
        except Exception as e:
            raise ValueError(f"Failed to delete tag '{tag_id}': {e}")

    def update_tag_timestamp(self, tag_id: str) -> None:
        """
        Update the updated_at timestamp for a tag.
        """
        tag = self._tag_store.get_tag_by_id(tag_id)
        tag.updated_at = datetime.now()
        self._tag_store.update_tag_by_id(tag_id, tag)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Util private methods

    def _retrieve_documents_for_tag(self, tag_id: str) -> list[DocumentMetadata]:
        """
        Retrieve the document associated with a tag.
        """
        return self.document_metadata_service.get_document_metadata_in_tag(tag_id)

    def _retrieve_prompts_for_tag(self, tag_id: str) -> list[Prompt]:
        """
        Retrieve the prompts associated with a tag.
        """
        return self.prompt_service.get_prompt_in_tag(tag_id)

    def _retrieve_document_ids_for_tag(self, tag_id: str) -> list[str]:
        """
        Retrieve the document IDs associated with a tag.
        """
        documents = self._retrieve_documents_for_tag(tag_id)
        return [doc.document_uid for doc in documents]

    def _retrieve_prompt_ids_for_tag(self, tag_id: str) -> list[str]:
        """
        Retrieve the document IDs associated with a tag.
        """
        prompts = self._retrieve_prompts_for_tag(tag_id)
        return [prompt.id for prompt in prompts]

    def _retrieve_documents_metadata(self, document_ids: list[str]) -> list[DocumentMetadata]:
        """
        Retrieve full document metadata for a list of document IDs.
        """
        metadata = []
        for doc_id in document_ids:
            # If document id doesn't exist, a `MetadataNotFound` exception will be raised
            metadata.append(self.document_metadata_service.get_document_metadata(doc_id))
        return metadata

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Helper methods for tag ID management in documents

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
