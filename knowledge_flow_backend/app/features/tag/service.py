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
from app.features.metadata.service import MetadataService
from app.features.tag.structure import Tag, TagCreate, TagUpdate
from fred_core import KeycloakUser


class TagService:
    """
    Service for Tag resource CRUD operations, user-scoped.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()

        self.document_metadata_service = MetadataService()

    def list_tags_for_user(self, user: KeycloakUser) -> list[Tag]:
        # Todo: check if user is authorized
        return self._tag_store.list_tags_for_user(user)

    def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> Tag:
        # Todo: check if user is authorized
        return self._tag_store.get_tag_by_id(tag_id)

    def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> Tag:
        # Todo: check if user is authorized to create tags

        # Check that document ids are valid
        self.validate_documents_ids(tag_data.document_ids)

        # Create tag from input data
        now = datetime.now()
        tag = Tag(
            name=tag_data.name,
            description=tag_data.description,
            type=tag_data.type,
            document_ids=tag_data.document_ids,
            # Set a unique id
            id=str(uuid4()),
            # Associate to user
            owner_id=user.uid,
            # Set timestamps
            created_at=now,
            updated_at=now,
        )

        return self._tag_store.create_tag(tag)

    def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> Tag:
        # Todo: check if user is authorized

        # Check that document ids are valid
        self.validate_documents_ids(tag_data.document_ids)

        # Retrieve the existing tag
        tag = self._tag_store.get_tag_by_id(tag_id)

        # Update tag with input data
        tag.name = tag_data.name
        tag.description = tag_data.description
        tag.type = tag_data.type
        tag.document_ids = tag_data.document_ids
        # Update the updated_at timestamp
        tag.updated_at = datetime.now()

        return self._tag_store.update_tag_by_id(tag_id, tag)

    def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        # Todo: check if user is authorized
        return self._tag_store.delete_tag_by_id(tag_id)

    def validate_documents_ids(self, document_ids: list[str]) -> None:
        for doc_id in document_ids:
            # If doucment id doesn't exist, a `MetadataNotFound` exeception will be raised
            _ = self.document_metadata_service.get_document_metadata(doc_id)

