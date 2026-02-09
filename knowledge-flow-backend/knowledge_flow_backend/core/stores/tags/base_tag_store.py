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

from abc import ABC, abstractmethod
from typing import List

from fred_core import KeycloakUser

from knowledge_flow_backend.features.tag.structure import Tag, TagType


class TagNotFoundError(Exception):
    """Raised when a tag is not found."""

    pass


class TagAlreadyExistsError(Exception):
    """Raised when trying to create a tag that already exists."""

    pass


class TagDeserializationError(Exception):
    """Raised when a stored tag cannot be deserialized."""

    pass


class BaseTagStore(ABC):
    """
    Abstract base class for storing and retrieving tags, user-scoped.

    Exceptions:
        - list_tags_for_user: (should not throw)
        - get_tag_by_id: TagNotFoundError if tag does not exist
        - create_tag: TagAlreadyExistsError if tag already exists
        - update_tag_by_id: TagNotFoundError if tag does not exist
        - delete_tag_by_id: TagNotFoundError if tag does not exist
    """

    @abstractmethod
    async def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        pass

    @abstractmethod
    async def get_tag_by_id(self, tag_id: str) -> Tag:
        """
        Retrieve a tag by its ID.
        Raises:
            TagNotFoundError: If the tag does not exist.
        """
        pass

    @abstractmethod
    async def get_by_owner_type_full_path(self, owner_id: str, tag_type: TagType, full_path: str) -> Tag | None:
        pass

    @abstractmethod
    async def create_tag(self, tag: Tag) -> Tag:
        pass

    @abstractmethod
    async def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        pass

    @abstractmethod
    async def delete_tag_by_id(self, tag_id: str) -> None:
        pass
